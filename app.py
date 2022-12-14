from operator import add
import sys


import os
import streamlit as st
import time
import json
import uuid
import mimetypes
from api_client import SfnApi, ApiError
from streamlit_cognito_auth import logger
import logging

logger = logging.getLogger(__name__)
logger.debug("app.py is reloading")

def url_download_hyperlink(label, url, filename=None, content_type=None):
  if filename is None:
    filename = url.split('/')[-1]
  if content_type is None:
    content_type, _ = mimetypes.guess_type(url)
    if content_type is None:
      content_type, _ = mimetypes.guess_type(filename)
  html = f"<a href='{url}'"
  if not content_type is None:
    html += f" type='{content_type}'"
  if filename is None:
    html += " download"
  else:
    html += f" download='{filename}'"
  html += f">{label}</a><br>"
  st.markdown(html, unsafe_allow_html=True)

st.title("Remote ML Pipeline Dashboard")

api = SfnApi()

auth = api.auth.update()

# make sidebar wider.  the default is 21rem
st.markdown(
    f'''<style>
        section[data-testid="stSidebar"] .css-ng1t4o {{width: 30rem;}}
        section[data-testid="stSidebar"] .css-1d391kg {{width: 30rem;}}
    </style>
''',
    unsafe_allow_html=True
  )

auth.button()
st.sidebar.markdown("""---""")

auth.require_verified_cognito_group('approved')

st.info(f"Yay! You are logged in to verified email address {auth.user_email}, and are in Cognito group 'approved'.")
#st.text(f"API info={json.dumps(api.api_info, indent=2, sort_keys=True)}")

jobid = api.jobid

worker_names = api.worker_names
default_worker_name = api.default_worker_name

run_button_pressed = st.sidebar.button('Run', help="Press to run the job")


def handle_stop():
  logger.info('STOP button was clicked (onclick)')
  result = api.stop_job()
  logger.info(f'Result of stop-job: {json.dumps(result, sort_keys=True)}')

stop_holder = st.sidebar.empty()

stop_button_enabled = True
stop_button_iter = 0
def enable_stop_button(enabled):
  global stop_button_enabled, stop_button_iter
  if enabled != stop_button_enabled:
    stop_holder.button('Stop', help="Press to abort the job", on_click=handle_stop, disabled=not enabled, key=f'stop_button_{stop_button_iter}')
    stop_button_enabled = enabled
    stop_button_iter += 1

enable_stop_button(False)

if 'SamMacbook' in worker_names:
  default_worker_name = 'SamMacbook'

i_default_worker = 0 if default_worker_name is None else worker_names.index(default_worker_name)
mdf = st.sidebar.radio if len(worker_names) <= 12 else st.sidebar.selectbox
worker_name = mdf(
    'Worker machine',
    options=worker_names,
    index=i_default_worker,
    help='Select the name of the worker machine that will execute the job')

prompt = st.sidebar.text_area(
    'Generation prompt',
    value="A cartoon image of a cat wearing a large sombrero and programming a computer at a desk in a dimly lit room.",
    placeholder='A cat dressed like Napolean...',
    help="The descriptive text that stable diffusion will use to generate images"
  )

n_samples = st.sidebar.slider('Number of samples', min_value=1, max_value=10, value=1, help="The number of images to generate")

seed = st.sidebar.number_input('Seed', min_value=0, max_value=65535, value=1024, help="The random seed for generation")

uploaded_files = st.sidebar.file_uploader("Upload Input Files", accept_multiple_files=True)


st.sidebar.markdown("""---""")
st.sidebar.header("Advanced")

default_script_text = """PROMPT="$(jq -r .prompt < input/task_data.json)"
SEED="$(jq -r .seed < input/task_data.json)"
N_SAMPLES="$(jq -r .n_samples < input/task_data.json)"
TASK_DIR="$(pwd)"
cd ../..
rm -fr ./outputs/txt2img-samples/
python3 scripts/txt2img.py \
  --prompt "$PROMPT" \
  --n_samples "$N_SAMPLES" \
  --n_iter 1 \
  --skip_grid \
  --plms \
  --outdir "$TASK_DIR/output"
"""

script_text = st.sidebar.text_area(
    'Script',
    value=default_script_text,
    placeholder='Bash script contents...',
    help="The script command(s) to run on the worker"
  )

default_additional_params = """{ }
"""

additional_params = st.sidebar.text_area(
    'Additional parameters',
    value=default_additional_params,
    placeholder="""JSON; e.g.: { "keep_task_dir": true }""",
    help="A JSON opject with key/value pairs to send as job params"
  )


submit_result = None
submit_attempted = False
submit_failed = False
if run_button_pressed:
  jobid = api.new_job()
  st.session_state['sfn_jobid'] = jobid
  st.info(f"Job ID={jobid}")
  if len(uploaded_files) > 0:
    with st.spinner("Uploading files to S3"):
      api.upload_job_input_files(uploaded_files)
  with st.spinner("Submitting job..."):
    data = dict(script=script_text, prompt=prompt, n_samples=n_samples, seed=seed)
    if additional_params.strip() != '':
      data.update(json.loads(additional_params))
    try:
      submit_attempted = True
      submit_result = api.start_job(data=data, worker_name=worker_name)
    except ApiError as e:
      submit_failed = True
      st.text(f"Job submission failed: {e}")
  enable_stop_button(True)

if not submit_result is None:
  with st.expander("Job submitted", expanded=False):
    st.text(json.dumps(submit_result, indent=2, sort_keys=True))

elif not jobid is None:
  st.info(f"Job ID={jobid}")

job_result = None
job_output = {}
if not jobid is None and not submit_failed:
  with st.spinner("Waiting for job to finish..."):
    with st.empty():
      i = 0
      while job_result is None or job_result.get('status', '') == 'RUNNING':
        i += 1
        st.info(f'... Long polling for job completion [{i}]')
        job_result = api.get_job_result(max_wait_seconds=2)
      if job_result is None:
        st.error('Could not get job result')
      else:
        job_status = job_result.get('status', None)
        if job_status == "RUNNING":
          enable_stop_button(True)
        job_output_str = job_result.get('output', "{}")
        job_output = json.loads(job_output_str)
        job_error = None
        if job_status is None:
          job_summary = "Job completed without status"
        elif job_status == 'SUCCEEDED':
          if 'JobError' in job_output:
            job_error = job_output['JobError']
            error_message = job_error.get('Error', 'Unspecified error')
            job_summary = f"Job completed with job error: {error_message}"
          else:
            job_summary = "Job SUCCEEDED"
        elif job_status == 'FAILED':
          job_sumary = "Job FAILED"
        else:
          job_summary = f"Job completed with status {job_status}"
        with st.expander(job_summary, expanded=False):
          st.text("job_result = " + json.dumps(job_result, indent=2, sort_keys=True))

  if len(job_output) > 0:
    with st.expander("Job output", expanded=True):
      st.text("job_output = " + json.dumps(job_output, indent=2, sort_keys=True))

  #logger.info('getting output file list')
  output_infos = api.get_job_outputs_metadata()
  #logger.info(f'back from getting output file list, len={len(output_infos)}')
  #st.text(f"output metadata={json.dumps(output_infos, indent=2, sort_keys=True)}")
  image_list = []
  if len(output_infos) > 0:
    with st.expander("Output files:", expanded=True):
      for output_info in output_infos:
        filename = output_info['filename']
        download_url = output_info['download_url']
        url_download_hyperlink(filename, download_url, filename=os.path.basename(filename))
        file_ext = os.path.splitext(filename)[1]
        #logger.warning(f"filename={filename} url={download_url}, file_ext={file_ext}")
        if file_ext in ('.jpg', '.jpeg', '.png'):
          #logger.warning(f"Adding {filename} to image_list")
          image_list.append(download_url)

  #logger.warning(f"image list len={len(image_list)}")
  if len(image_list) > 0:
    with st.expander("Output images:", expanded=True):
      st.image(image_list)

logger.debug("app.py is done loading")
