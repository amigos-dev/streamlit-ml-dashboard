import streamlit as st
import time
import sys
import json
from streamlit_ml_dashboard import authenticate

authenticate.set_st_state_vars()

# Add login/logout buttons
authenticate.auth_ui()


st.write(f'login_link="{authenticate.login_link}"')

st.write(f"user_info={json.dumps(authenticate.get_user_info(), sort_keys=True, indent=2)}")
st.write(f"id_token_payload={json.dumps(authenticate.get_id_token_payload(), sort_keys=True, indent=2)}")
st.write(f"cognito_groups={json.dumps(authenticate.get_user_cognito_groups(), sort_keys=True, indent=2)}")

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
