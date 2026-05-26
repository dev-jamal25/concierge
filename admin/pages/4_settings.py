import requests
import streamlit as st


st.title("Settings")

api_base = st.session_state.get("api_base", "http://localhost:8000")
token = st.session_state.get("access_token", "")
headers = {"authorization": f"Bearer {token}"}

if not token:
    st.info("Add a tenant admin bearer token on the main page.")
else:
    tenant_response = requests.get(f"{api_base}/admin/tenant", headers=headers, timeout=10)
    guardrails_response = requests.get(
        f"{api_base}/admin/guardrails", headers=headers, timeout=10
    )
    origins_response = requests.get(f"{api_base}/admin/origins", headers=headers, timeout=10)

    if tenant_response.ok:
        tenant = tenant_response.json()
        st.subheader("Tenant")
        persona = st.text_area("Persona JSON", value=str(tenant.get("persona_config", {})))
        theme = st.text_area("Theme JSON", value=str(tenant.get("theme_config", {})))
        st.caption("JSON editing is a placeholder until form controls are finalized.")

    if guardrails_response.ok:
        st.subheader("Guardrails")
        st.json(guardrails_response.json())

    st.subheader("Allowed origins")
    if origins_response.ok:
        st.dataframe(origins_response.json(), use_container_width=True)

    new_origin = st.text_input("Add origin", placeholder="https://example.com")
    if st.button("Add origin", disabled=not new_origin):
        response = requests.post(
            f"{api_base}/admin/origins",
            json={"origin": new_origin},
            headers=headers,
            timeout=10,
        )
        if response.ok:
            st.success("Origin added.")
        else:
            st.error("Could not add origin.")
