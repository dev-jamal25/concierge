import streamlit as st

from api_client import AdminAPI, error_message, require_token
from config import default_api_base_url

st.title("Leads")

api_base = st.session_state.get("api_base", default_api_base_url())
token = st.session_state.get("access_token", "")

if not require_token(token):
    st.info("Add a tenant admin bearer token on the main page.")
    st.stop()

api = AdminAPI(api_base, token)
since = st.text_input("Since filter (optional ISO datetime)", placeholder="2026-05-30T00:00:00Z")
leads_result = api.get("/leads", since=since)

if leads_result.route_missing:
    st.warning(error_message(leads_result, route_name="Leads"))
    st.stop()
if not leads_result.ok:
    st.error(error_message(leads_result, route_name="Leads"))
    st.stop()

leads = leads_result.data if isinstance(leads_result.data, list) else []
st.metric("Captured leads", len(leads))

if leads:
    st.dataframe(
        [
            {
                "created_at": lead.get("created_at"),
                "name": lead.get("name"),
                "contact": lead.get("contact"),
                "intent": lead.get("intent"),
                "conversation_id": lead.get("conversation_id"),
            }
            for lead in leads
        ],
        use_container_width=True,
        hide_index=True,
    )
else:
    st.info("No leads captured for this tenant yet.")

export_result = api.get("/leads/export", since=since)
if export_result.ok and isinstance(export_result.data, str):
    st.download_button(
        "Download CSV",
        data=export_result.data,
        file_name="leads.csv",
        mime="text/csv",
    )
elif export_result.route_missing:
    st.warning(error_message(export_result, route_name="Lead export"))
else:
    st.caption("CSV export is unavailable for the current filter or token.")
