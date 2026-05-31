import streamlit as st

from api_client import AdminAPI, error_message
from auth import require_auth

st.title("CMS")

api_base, token = require_auth()

api = AdminAPI(api_base, token)
pages_result = api.get("/cms/pages")

if pages_result.route_missing:
    st.warning(error_message(pages_result, route_name="CMS"))
    st.stop()
if not pages_result.ok:
    st.error(error_message(pages_result, route_name="CMS"))
    st.stop()

pages = pages_result.data if isinstance(pages_result.data, list) else []

st.subheader("Pages")
if pages:
    st.dataframe(
        [
            {
                "id": page.get("id"),
                "title": page.get("title"),
                "slug": page.get("slug"),
                "state": page.get("state"),
                "updated_at": page.get("updated_at"),
            }
            for page in pages
        ],
        use_container_width=True,
        hide_index=True,
    )
else:
    st.info("No CMS pages yet.")

st.subheader("Create Page")
with st.form("create-cms-page"):
    title = st.text_input("Title")
    slug = st.text_input("Slug")
    body = st.text_area("Body", height=220)
    create = st.form_submit_button("Create draft")

if create:
    if not title or not slug or not body:
        st.warning("Title, slug, and body are all required.")
    else:
        result = api.post("/cms/pages", {"title": title, "slug": slug, "body": body})
        if result.ok:
            st.success("Draft page created. Refresh the page to see it in the list.")
        else:
            st.error(error_message(result, route_name="Create CMS page"))

st.subheader("Edit Existing Page")
if not pages:
    st.caption("Create a draft first.")
    st.stop()

page_by_label = {
    f"{page.get('title')} [{page.get('state')}]": page for page in pages
}
selected_label = st.selectbox("Page", list(page_by_label.keys()))
selected = page_by_label[selected_label]
page_id = selected["id"]

with st.form("edit-cms-page"):
    updated_title = st.text_input("Title", value=selected.get("title", ""))
    updated_body = st.text_area("Body", value=selected.get("body", ""), height=260)
    update = st.form_submit_button("Save changes")

if update:
    result = api.put(
        f"/cms/pages/{page_id}",
        {"title": updated_title, "body": updated_body},
    )
    if result.ok:
        st.success("Page updated. Refresh the page to see the latest values.")
    else:
        st.error(error_message(result, route_name="Update CMS page"))

actions = st.columns(3)
if actions[0].button("Publish selected page"):
    result = api.post(f"/cms/pages/{page_id}/publish")
    if result.ok:
        st.success("Publish accepted. Reindexing uses the configured embedding provider.")
    else:
        st.error(error_message(result, route_name="Publish CMS page"))

if actions[1].button("Unpublish selected page"):
    result = api.post(f"/cms/pages/{page_id}/unpublish")
    if result.ok:
        st.success("Unpublish accepted.")
    else:
        st.error(error_message(result, route_name="Unpublish CMS page"))

if actions[2].button("Delete selected draft"):
    result = api.delete(f"/cms/pages/{page_id}")
    if result.ok:
        st.success("Draft deleted.")
    else:
        st.error(error_message(result, route_name="Delete CMS page"))
