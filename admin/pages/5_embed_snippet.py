import streamlit as st


st.title("Embed Snippet")

api_base = st.session_state.get("api_base", "http://localhost:8000")
widget_id = st.text_input("Widget public id", placeholder="wgt_pub_...")

snippet = f"""<script
  src="{api_base}/widget.js"
  data-widget-id="{widget_id}"
  data-position="bottom-right"
  async
></script>"""

st.code(snippet, language="html")
