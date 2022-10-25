import os
from pickle import TRUE
import sys
import streamlit as st
from dotenv import load_dotenv
import requests
import base64
import json
import urllib.parse

load_dotenv()
COGNITO_DOMAIN = os.environ.get("COGNITO_DOMAIN") or "https://amigos-users.auth.us-west-2.amazoncognito.com"
CLIENT_ID = os.environ.get("CLIENT_ID")
CLIENT_SECRET = os.environ.get("CLIENT_SECRET")
APP_URI = os.environ.get("APP_URI") or "http://localhost:8501/"

ESCAPED_APP_URI = urllib.parse.quote(APP_URI.encode('utf8'))

DEBUG = 'localhost' in APP_URI

def dp(*args, **kwargs):
    if DEBUG:
      print(*args, **kwargs, file=sys.stderr)

def initialise_st_state_vars():
    """
    Initialise Streamlit state variables.

    Returns:
        Nothing.
    """
    dp(f"initialise_st_state_vars with session_state={dict(st.session_state)}")
    if "id_token" not in st.session_state:
        st.session_state["id_token"] = ""
    if "access_token" not in st.session_state:
        st.session_state["access_token"] = ""
    if "auth_code" not in st.session_state:
        st.session_state["auth_code"] = ""
    if "authenticated" not in st.session_state:
        st.session_state["authenticated"] = False
    if "user_info" not in st.session_state:
        st.session_state["user_info"] = None
    if "user_cognito_groups" not in st.session_state:
        st.session_state["user_cognito_groups"] = []

def clear_login_cache():
    """
    Reset Streamlit state variables associated with login.

    Returns:
        Nothing.
    """
    dp(f"clear_login_cache!")
    st.session_state["id_token"] = ""
    st.session_state["access_token"] = ""
    st.session_state["auth_code"] = ""
    st.session_state["authenticated"] = False
    st.session_state["user_info"] = None
    st.session_state["user_cognito_groups"] = []

def get_and_clear_auth_code():
    """
    Gets auth_code state variable, and clears it from browser address bar.

    Returns:
        str: auth code, or "".
    """
    auth_code = ""
    update_query_params = False
    query_params = dict(st.experimental_get_query_params())
    if "action" in query_params and query_params["action"][0] == "logout":
        dp("Redirected back from logout")
        clear_login_cache()
        del query_params['action']
        update_query_params = True
    if "code" in query_params:
        auth_code = query_params["code"][0]
        del query_params["code"]
        update_query_params = True
        if auth_code == st.session_state["auth_code"]:
            dp(f"Duplicate auth code found in query params: {auth_code}")
            auth_code = ""
        else:
            dp(f"New auth code found in query params: {auth_code}")
            st.session_state["auth_code"] = auth_code
    if update_query_params:
        st.experimental_set_query_params(**query_params)
    return auth_code

# -------------------------------------------------------
# Use authorization code to get user access and id tokens
# -------------------------------------------------------
def get_user_tokens(auth_code=""):
    """
    Gets user tokens by making a post request call.

    Args:
        auth_code: New authorization code from cognito server, or "" to use cached tokens.

    Returns:
        tuple(
          'access_token': access token from cognito server if user is successfully authenticated, or "".
          'id_token': access token from cognito server if user is successfully authenticated, or "".
        )
    """
    if auth_code == "":
        access_token = st.session_state.get("access_token", "")
        id_token = st.session_state.get("id_token", "")
    else:
        # Variables to make a post request
        token_url = f"{COGNITO_DOMAIN}/oauth2/token"
        client_secret_string = f"{CLIENT_ID}:{CLIENT_SECRET}"
        client_secret_encoded = str(
            base64.b64encode(client_secret_string.encode("utf-8")), "utf-8"
        )
        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Authorization": f"Basic {client_secret_encoded}",
        }
        body = {
            "grant_type": "authorization_code",
            "client_id": CLIENT_ID,
            "code": auth_code,
            "redirect_uri": APP_URI,
        }

        token_response = requests.post(token_url, headers=headers, data=body)
        try:
            trj = token_response.json()
            access_token = trj["access_token"]
            id_token = trj["id_token"]
        except (KeyError, TypeError):
            access_token = ""
            id_token = ""
        st.session_state["access_token"] = access_token
        st.session_state["id_token"] = id_token

    return access_token, id_token


# ---------------------------------------------
# Use access token to retrieve user information
# ---------------------------------------------
def get_user_info():
    """
    Gets user info from aws cognito server.

    Returns:
        userinfo_response: json object.
    """
    dp(f"getting user_info with session_state={dict(st.session_state)}")
    result = st.session_state.get("user_info", None)
    if result is None:
        access_token = st.session_state['access_token']
        if not access_token is None and access_token != '':
            dp(f"getting user_info with access_token={access_token}")
            userinfo_url = f"{COGNITO_DOMAIN}/oauth2/userInfo"
            headers = {
                "Content-Type": "application/json;charset=UTF-8",
                "Authorization": f"Bearer {access_token}",
            }

            userinfo_response = requests.get(userinfo_url, headers=headers)
            result = userinfo_response.json()
            dp(f"user_info response={json.dumps(result, sort_keys=True, indent=2)}")
            st.session_state['user_info'] = result
    return result

# -------------------------------------------------------
# Decode access token to JWT to get user's cognito groups
# -------------------------------------------------------
# Ref - https://gist.github.com/GuillaumeDerval/b300af6d4f906f38a051351afab3b95c
def pad_base64(data):
    """
    Makes sure base64 data is padded.

    Args:
        data: base64 token string.

    Returns:
        data: padded token string.
    """
    missing_padding = len(data) % 4
    if missing_padding != 0:
        data += "=" * (4 - missing_padding)
    return data


def get_id_token_payload():
    """
    Decode id token

    Returns:
        Optional[JsonableDict]: the deserialized token payload.
    """
    result = None
    id_token = st.session_state['id_token']
    if not id_token is None and id_token != "":
        header, payload, signature = id_token.split(".")
        printable_payload = base64.urlsafe_b64decode(pad_base64(payload))
        result = json.loads(printable_payload)
    return result

def get_user_email():
    result = None
    idtp = get_id_token_payload()
    if not idtp is None and "email" in idtp:
        result = str(idtp['email'])
    return result

def user_email_is_verified():
    result = False
    idtp = get_id_token_payload()
    if not idtp is None and "email_verified" in idtp:
        result = not not idtp['email_verified']
    return result

def user_is_authenticated():
    result = st.session_state.get('authenticated', None)
    if result is None:
        result = not get_user_email() is None
        st.session_state['authenticated'] = result
    return result

def get_verified_user_email():
    return None if not user_email_is_verified() else get_user_email()

def get_user_cognito_groups():
    """
    Decode id token to get user cognito groups.

    Returns:
        user_cognito_groups: a list of all the cognito groups the user belongs to.
    """
    user_cognito_groups = st.session_state.get("user-cognito-groups", None)
    if user_cognito_groups is None:
        user_cognito_groups = []
        payload_dict = get_id_token_payload()
        if not payload_dict is None:
            try:
                user_cognito_groups = list(payload_dict["cognito:groups"])
            except (KeyError, TypeError):
                pass
        st.session_state["user_cognito_groups"] = user_cognito_groups
    return user_cognito_groups

# -----------------------------
# Set Streamlit state variables
# -----------------------------
def set_st_state_vars():
    """
    Sets the streamlit state variables after user authentication.
    Returns:
        Nothing.
    """
    dp("Enter set_st_state_vars")
    initialise_st_state_vars()
    auth_code = get_and_clear_auth_code()
    if not auth_code is None and auth_code != "":
        dp(f"set_st_state_vars: new auth code, resetting: {auth_code}")
        clear_login_cache()
        get_user_tokens(auth_code)

    # populate session state if necessary
    get_user_cognito_groups()
    user_is_authenticated()
    dp("Exit set_st_state_vars")

# -----------------------------
# Login/ Logout HTML components
# -----------------------------
login_link = f"{COGNITO_DOMAIN}/login?client_id={CLIENT_ID}&response_type=code&scope=email+openid&redirect_uri={ESCAPED_APP_URI}"
logout_link = f"{COGNITO_DOMAIN}/logout?client_id={CLIENT_ID}&logout_uri={ESCAPED_APP_URI}%3Faction%3Dlogout"

html_css_login = """
<style>
.button-login {
  background-color: skyblue;
  color: white !important;
  padding: 1em 1.5em;
  text-decoration: none;
  text-transform: uppercase;
}

.button-login:hover {
  background-color: #555;
  text-decoration: none;
}

.button-login:active {
  background-color: black;
}

</style>
"""

html_button_login = (
    html_css_login
    + f"<a href='{login_link}' class='button-login' target='_self'>Log In</a>"
)
html_button_logout = (
    html_css_login
    + f"<a href='{logout_link}' class='button-login' target='_self'>Log Out</a>"
)


def button_login():
    """

    Returns:
        Html of the login button.
    """
    return st.sidebar.markdown(f"{html_button_login}", unsafe_allow_html=True)


def button_logout():
    """

    Returns:
        Html of the logout button.
    """
    #clear_login_cache()
    return st.sidebar.markdown(f"{html_button_logout}", unsafe_allow_html=True)

def auth_ui():
    email = get_user_email()
    if not email is None:
        st.sidebar.write(f"Welcome, {email}")
        button_logout()
    else:
        button_login()

def auth_button():
    if user_is_authenticated():
        button_logout()
    else:
        button_login()
