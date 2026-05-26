import streamlit as st

st.set_page_config(page_title="Concierge Admin", layout="wide")

st.title("Concierge Admin")
st.caption("Owner D Streamlit admin surface")

st.write("Use the sidebar pages to review dashboard, CMS, leads, settings, and embed snippet.")

api_base = st.text_input("API base URL", value="http://localhost:8000")
access_token = st.text_input("Tenant admin bearer token", type="password")

st.session_state["api_base"] = api_base.rstrip("/")
st.session_state["access_token"] = access_token
