from typing import Optional, Dict, List, Union, Iterable

import sys
import os
import time
import json
import requests
import logging
import uuid

from requests import Response
import urllib.parse as urlparse
from urllib.parse import urlencode

import streamlit as st
from streamlit.runtime.uploaded_file_manager import UploadedFile

from streamlit_cognito_auth import cognito_auth, CognitoAuth, JsonableDict

logger = logging.getLogger(__name__)

api_uri = os.environ['API_URI']
if not api_uri.endswith('/'):
  api_uri += '/'

DEBUG_JOBID = os.environ.get('DEBUG_JOBID', None)
if DEBUG_JOBID == '':
  DEBUG_JOBID = None

'''
    "errorMessage": "POST not handled for request path: 'download-job-outputs2'",
    "errorType": "RuntimeError",
    "stackTrace": [
      "Traceback (most recent call last):",
      "  File \"/var/task/app.py\", line 244, in handler",
      "    raise RuntimeError(f\"POST not handled for request path: '{reqpath}'\")",
      "RuntimeError: POST not handled for request path: 'download-job-outputs2'",
      ""
    ],
'''
class ApiError(RuntimeError):
  api_error_data: JsonableDict

  def __init__(self, data: JsonableDict):
    self.api_error_data = data
    msg = ''
    if 'errorType' in data:
      msg += data['errorType'] + ': '
    if 'errorMessage' in data:
      msg += data['errorMessage']
    else:
      msg += "An error occurred during request execution"
    if 'stackTrace' in data:
      msg += "\n  Remote " + '\n  '.join(data['stackTrace'])
    super().__init__(msg)

class SfnJobSessionState:
  jobid: Optional[str] = None
  output_infos: Optional[List[JsonableDict]] = None

  def __init__(self):
    pass

class SfnSessionState:
  api_info: Optional[JsonableDict] = None
  job: SfnJobSessionState

  def __init__(self):
    self.job = SfnJobSessionState()

class SfnApi:
  auth: CognitoAuth

  def __init__(self, auth: Optional[CognitoAuth] = None):
    if auth is None:
      auth = cognito_auth()
    self.auth = auth

  @property
  def session_state(self) -> SfnSessionState:
    result = st.session_state.get('sfn_api', None)
    if result is None:
      result = SfnSessionState()
      st.session_state['sfn_api'] = result
    return result

  def response_value(self, response: Response) -> JsonableDict:
    response.raise_for_status()
    result = response.json()
    if 'apiError' in result:
      raise ApiError(result['apiError'])
    logger.info(f"invoke response: {json.dumps(result)}")
    return result

  def invoke_get(self, name: str, **kwargs) -> JsonableDict:
    uri = urlparse.urljoin(api_uri, name)
    #url_parts = list(urlparse.urlparse(url))
    #query = urlparse.parse_qs(url_parts[4], keep_blank_values=True))
    #query.update(kwargs)
    #url_parts[4] = urlencode(query, doseq=True)
    #uri = urlparse.urlunparse(url_parts)
    headers: Dict[str, str] = {}
    access_token = self.auth.access_token
    if not access_token is None:
      headers["Authorization"] = access_token

    logger.info(f"invoke_get({name}): params={kwargs}")
    response = requests.get(uri, headers=headers, params=kwargs)
    return self.response_value(response)

  def invoke_post(self, name: str, **kwargs) -> JsonableDict:
    uri = urlparse.urljoin(api_uri, name)
    body = json.dumps(kwargs)
    logger.info(f"invoke_post({name}): body={body}")
    headers: Dict[str, str] = { 'Content-Type': 'application/json' }
    access_token = self.auth.access_token
    if not access_token is None:
      headers["Authorization"] = access_token

    response = requests.post(uri, headers=headers, data=body)
    return self.response_value(response)

  @property
  def api_info(self) -> JsonableDict:
    ss = self.session_state
    result = ss.api_info
    if result is None:
      result = self.invoke_get("info")
      ss.api_info = result
    return result

  @property
  def aws_region(self) -> str:
    return self.api_info['aws_region']

  @property
  def jobs_s3_uri(self) -> List[str]:
    return self.api_info['jobs_s3_uri']

  @property
  def worker_names(self) -> List[str]:
    return self.api_info['worker_names']

  @property
  def default_worker_name(self) -> Optional[str]:
    return self.api_info['default_worker_name']

  @property
  def state_machine_arn(self) -> str:
    return self.api_info['state_machine_arn']

  @property
  def deployment_stage(self) -> str:
    return self.api_info['stage']

  @property
  def job(self) -> Optional[str]:
    return self.session_state.job

  @property
  def jobid(self) -> Optional[str]:
    return self.session_state.job.jobid

  @jobid.setter
  def jobid(self, jobid: Optional[str]) -> None:
    if jobid == '':
      jobid = None
    ss = self.session_state
    if jobid is None or jobid != ss.job.jobid:
      job = SfnJobSessionState()
      job.jobid = jobid
      ss.job = job

  def new_job(self) -> str:
    self.jobid = None
    jobid = DEBUG_JOBID if not DEBUG_JOBID is None else str(uuid.uuid4())
    self.jobid = jobid
    return jobid

  def clear_job(self) -> None:
    self.jobid = None

  def require_job(self) -> SfnJobSessionState:
    job = self.job
    if job.jobid is None:
      raise RuntimeError("A Job ID is required")
    return job

  def require_jobid(self) -> str:
    job = self.require_job()
    return job.jobid

  def get_job_input_upload_metadata(self, filenames: List[str]) -> List[JsonableDict]:
    jobid = self.require_jobid()
    resp = self.invoke_post("upload-job-inputs", jobid=jobid, filename_list=filenames)
    return resp['upload_infos']

  def upload_job_input_files(self, uploaded_files: Union[UploadedFile, Iterable[UploadedFile]]) -> None:
    jobid = self.require_jobid()
    if isinstance(uploaded_files, UploadedFile):
      uploaded_files = [ uploaded_files ]

    if len(uploaded_files) > 0:
      filenames = [ x.name for x in uploaded_files ]
      upload_infos = self.get_job_input_upload_metadata(filenames)

      for i, uploaded_file in enumerate(uploaded_files):
        #filename = uploaded_file.name
        upload_metadata = upload_infos[i]
        files = dict(file=uploaded_file)
        resp = requests.post(upload_metadata['url'], data=upload_metadata['fields'], files=files)
        resp.raise_for_status()

  def get_job_outputs_metadata(self, include_download_url: bool=True, refresh: bool=False) -> List[JsonableDict]:
    job = self.require_job()
    jobid = job.jobid
    result = job.output_infos
    if result is None or refresh:
      job.output_infos = None
      resp = self.invoke_post("list-job-outputs", jobid=jobid, include_download_url='1' if include_download_url else '')
      result = resp['file_infos']
      job.output_infos = result
    return result

  def start_job(
        self,
        data: JsonableDict,
        worker_name: Optional[str]=None,
        trace_header: Optional[str]=None,
      ):
    jobid = self.require_jobid()
    result = self.invoke_post('start-job', jobid=jobid, data=data, worker_name=worker_name, trace_header=trace_header)
    return result

  def get_job_result(
        self,
        polling_interval_seconds: Optional[float]=None,
        max_wait_seconds: Optional[float]=None,
      ) -> JsonableDict:
    jobid = self.require_jobid()
    result = self.invoke_post(
        'get-job-result',
        jobid=jobid,
        polling_interval_seconds=polling_interval_seconds,
        max_wait_seconds=max_wait_seconds
      )
    return result
  