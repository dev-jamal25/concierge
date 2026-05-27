import requests
import streamlit as st


st.title("Dashboard")

api_base = st.session_state.get("api_base", "http://localhost:8000")
token = st.session_state.get("access_token", "")

if not token:
    st.info("Add a tenant admin bearer token on the main page.")
else:
    response = requests.get(
        f"{api_base}/admin/tenant",
        headers={"authorization": f"Bearer {token}"},
        timeout=10,
    )
    if response.ok:
        tenant = response.json()
        st.metric("Tenant", tenant["display_name"])
        st.metric("Plan", tenant["plan"])
    else:
        st.error("Could not load tenant dashboard.")
