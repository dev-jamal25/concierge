import streamlit as st

from api_client import AdminAPI, error_message, require_token
from config import default_api_base_url, public_api_base_url


st.title("Embed Snippet")

api_base = st.session_state.get("api_base", default_api_base_url())
token = st.session_state.get("access_token", "")

if not require_token(token):
    st.info("Add a tenant admin bearer token on the main page.")
    st.stop()

api = AdminAPI(api_base, token)

# Try to auto-load the widget_id from the backend
widget_info_result = api.get("/admin/widget")
auto_widget_id = None
if widget_info_result.ok and isinstance(widget_info_result.data, dict):
    auto_widget_id = widget_info_result.data.get("widget_id")
elif not widget_info_result.route_missing:
    st.warning(error_message(widget_info_result, route_name="Widget info"))

public_api_base = st.text_input("Public API base URL", value=public_api_base_url())
widget_id = st.text_input(
    "Widget public ID",
    value=auto_widget_id or "",
    placeholder="lumiere-widget-v1",
)
position = st.selectbox("Position", ["bottom-right", "bottom-left"])

if not widget_id:
    st.info("Widget public ID is needed to generate the embed snippet.")
else:
    api_src = public_api_base.rstrip("/")
    snippet = f"""<script
  src="{api_src}/widget.js"
  data-widget-id="{widget_id}"
  data-position="{position}"
  async
></script>"""

    st.code(snippet, language="html")
    st.caption("The host page origin must be present in this tenant's allowed origins (see Settings).")

    st.subheader("Plain HTML Test Harness")
    st.code(
        f"""<!doctype html>
<html>
  <head><title>Concierge Widget Test</title></head>
  <body>
    <h1>Widget host page</h1>
{snippet}
  </body>
</html>""",
        language="html",
    )
