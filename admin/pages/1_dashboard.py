import streamlit as st

from api_client import AdminAPI, error_message
from auth import require_auth

st.title("Dashboard")

api_base, token = require_auth()

api = AdminAPI(api_base, token)
health = AdminAPI(api_base).get("/healthz")
tenant_result = api.get("/admin/tenant")
cms_result = api.get("/cms/pages")
leads_result = api.get("/leads")
escalations_result = api.get("/admin/escalations")

st.subheader("Backend")
if health.ok:
    st.success(f"API healthy at {api_base}")
else:
    st.error(error_message(health, route_name="Backend health"))

st.subheader("Tenant")
if tenant_result.ok and isinstance(tenant_result.data, dict):
    tenant = tenant_result.data
    metrics = st.columns(4)
    metrics[0].metric("Tenant", tenant.get("display_name", "Unknown"))
    metrics[1].metric("Slug", tenant.get("slug", "Unknown"))
    metrics[2].metric("Plan", tenant.get("plan", "Unknown"))
    metrics[3].metric("Tenant ID", tenant.get("id", "Unknown"))
else:
    st.error(error_message(tenant_result, route_name="Tenant dashboard"))

st.subheader("Activity")
activity = st.columns(3)
activity[0].metric(
    "CMS Pages",
    len(cms_result.data) if cms_result.ok and isinstance(cms_result.data, list) else "n/a",
)
activity[1].metric(
    "Leads",
    len(leads_result.data) if leads_result.ok and isinstance(leads_result.data, list) else "n/a",
)
activity[2].metric(
    "Escalations",
    (
        len(escalations_result.data)
        if escalations_result.ok and isinstance(escalations_result.data, list)
        else "n/a"
    ),
)

for label, result in (
    ("CMS pages", cms_result),
    ("Leads", leads_result),
    ("Escalations", escalations_result),
):
    if not result.ok:
        st.warning(error_message(result, route_name=label))
