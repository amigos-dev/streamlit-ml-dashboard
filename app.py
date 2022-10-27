import sys

print("app.py is loading", file=sys.stderr)

import streamlit as st
import time
import json
from streamlit_cognito_auth import cognito_auth

auth = cognito_auth().update()

auth.button()

st.write(f"ID token payload={json.dumps(auth.id_token_payload)}")
st.write(f"user_info={json.dumps(auth.get_user_info())}")

auth.require_verified()

st.info(f"Yay! You are logged in to verified email address {auth.user_email}, and are in these Cognito groups: {auth.cognito_groups}")

st.sidebar.text_input(
    'Prompt',
    placeholder='Image generation prompt string...',
    help="The test description that stable diffusion will use to generate images"
  )

st.sidebar.slider('# Samples', min_value=1, max_value=10, value=4, help="The number of images to generate")

st.sidebar.number_input('Seed', min_value=0, max_value=65535, help="The random seed for generation")

if st.sidebar.button('Run', help="Press to run the job"):
  with st.spinner("Generating images..."):
    with st.expander("Log output"):
      for i in range(10):
        st.info(f'... working {i}')
        time.sleep(1.0)

  st.info('Job completed!')

  image_list = [
    'https://images.unsplash.com/photo-1574144611937-0df059b5ef3e?ixlib=rb-1.2.1&ixid=MnwxMjA3fDB8MHxwaG90by1wYWdlfHx8fGVufDB8fHx8&auto=format&fit=crop&w=1064&q=80',
    'https://media.istockphoto.com/photos/cat-astronaut-in-space-on-background-of-the-globe-elements-of-this-picture-id898916122',
    'https://i.etsystatic.com/20122861/r/il/580164/3111232858/il_1588xN.3111232858_2vyl.jpg',
    'https://i.etsystatic.com/6560690/r/il/7dc5e4/3539984797/il_1588xN.3539984797_s1d6.jpg',
  ]

  st.image(image_list)

print("app.py is done loading", file=sys.stderr)
