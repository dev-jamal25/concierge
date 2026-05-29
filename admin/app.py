import requests
import streamlit as st

from api_client import AdminAPI, error_message
from config import default_api_base_url

st.set_page_config(page_title="Concierge Admin", layout="wide")

st.title("Concierge Admin")
st.caption("Owner D Streamlit admin surface")

st.write("Use the sidebar pages to manage CMS content, leads, tenant settings, and embed snippets.")

api_base = st.text_input("API base URL", value=default_api_base_url())
access_token = st.session_state.get("access_token", "")

with st.expander("Tenant admin login", expanded=not access_token):
    st.caption("Uses the real `/auth/login` route. You can also paste a bearer token below.")
    email = st.text_input("Email")
    password = st.text_input("Password", type="password")
    if st.button("Log in", disabled=not email or not password):
        login = AdminAPI(api_base).post("/auth/login", {"email": email, "password": password})
        if login.ok and isinstance(login.data, dict):
            access_token = str(login.data.get("access_token", ""))
            st.session_state["access_token"] = access_token
            st.success("Logged in.")
        else:
            st.error(error_message(login, route_name="Auth login"))

access_token = st.text_input(
    "Tenant admin bearer token",
    value=access_token,
    type="password",
)

st.session_state["api_base"] = api_base.rstrip("/")
st.session_state["access_token"] = access_token

st.subheader("Backend API")
try:
    response = requests.get(f"{st.session_state['api_base']}/healthz", timeout=5)
    if response.ok:
        st.success(f"Connected to {st.session_state['api_base']}")
    else:
        st.warning(f"API responded with HTTP {response.status_code}")
except requests.RequestException:
    st.error(f"Could not reach {st.session_state['api_base']}")

st.subheader("Tenant Summary")
if not access_token:
    st.info("Log in or paste a tenant admin bearer token to load tenant-scoped data.")
else:
    api = AdminAPI(st.session_state["api_base"], access_token)
    tenant_result = api.get("/admin/tenant")
    cms_result = api.get("/cms/pages")
    leads_result = api.get("/leads")
    escalations_result = api.get("/admin/escalations")

    if tenant_result.ok and isinstance(tenant_result.data, dict):
        tenant = tenant_result.data
        metrics = st.columns(4)
        metrics[0].metric("Tenant", tenant.get("display_name", "Unknown"))
        metrics[1].metric("Plan", tenant.get("plan", "Unknown"))
        metrics[2].metric(
            "CMS Pages",
            len(cms_result.data) if cms_result.ok and isinstance(cms_result.data, list) else "n/a",
        )
        metrics[3].metric(
            "Leads",
            len(leads_result.data) if leads_result.ok and isinstance(leads_result.data, list) else "n/a",
        )
        if escalations_result.ok and isinstance(escalations_result.data, list):
            st.caption(f"Escalated conversations: {len(escalations_result.data)}")
    else:
        st.error(error_message(tenant_result, route_name="Tenant summary"))

st.subheader("Admin Areas")
columns = st.columns(4)
columns[0].info("CMS: list, create, edit, publish, unpublish, and delete draft pages.")
columns[1].info("Leads: list captured leads and download CSV export.")
columns[2].info("Settings: edit tenant display, widget greeting/theme, and guardrails.")
columns[3].info("Embed snippet: generate the script tag for a widget public ID.")
