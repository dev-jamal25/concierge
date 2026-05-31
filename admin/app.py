import requests
import streamlit as st

from api_client import AdminAPI, error_message
from auth import clear_session, fetch_identity, persist_session, restore_session
from config import default_api_base_url

st.set_page_config(page_title="Concierge Admin", layout="wide")

restore_session()

token: str = st.session_state.get("access_token", "")
api_base: str = st.session_state.get("api_base", default_api_base_url())

# ── Authenticated view ─────────────────────────────────────────────────────────
if token:
    identity = st.session_state.get("identity", {})

    # Sidebar: identity + logout
    with st.sidebar:
        if identity:
            st.caption(
                f"**{identity.get('email', '')}**  \n"
                f"Role: {identity.get('role', '')}  \n"
                f"Tenant: {identity.get('tenant_id', 'n/a')}"
            )
        if st.button("Logout", key="main_logout"):
            clear_session()
            st.rerun()

    st.title("Concierge Admin")
    st.caption("Use the sidebar pages to manage CMS content, leads, tenant settings, and embed snippets.")

    # Health check
    st.subheader("Backend API")
    try:
        response = requests.get(f"{api_base}/healthz", timeout=5)
        if response.ok:
            st.success(f"Connected to {api_base}")
        else:
            st.warning(f"API responded with HTTP {response.status_code}")
    except requests.RequestException:
        st.error(f"Could not reach {api_base}")

    # Tenant summary
    st.subheader("Tenant Summary")
    api = AdminAPI(api_base, token)
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
    elif tenant_result.status_code == 401:
        # Token in cookie has expired — clear it and prompt re-login
        clear_session()
        st.warning("Your session has expired. Please sign in again.")
        st.rerun()
    else:
        st.error(error_message(tenant_result, route_name="Tenant summary"))

    st.subheader("Admin Areas")
    columns = st.columns(4)
    columns[0].info("CMS: list, create, edit, publish, unpublish, and delete draft pages.")
    columns[1].info("Leads: list captured leads and download CSV export.")
    columns[2].info("Settings: edit tenant display, widget greeting/theme, and guardrails.")
    columns[3].info("Embed snippet: generate the script tag for a widget public ID.")

# ── Login view ─────────────────────────────────────────────────────────────────
else:
    st.title("Concierge Admin — Sign In")

    login_tab, token_tab = st.tabs(["🔐 Admin Login", "🎟️ Tenant Token Login"])

    # ── Admin Login ──────────────────────────────────────────────────────────
    with login_tab:
        st.caption(
            "Sign in with your tenant admin email and password.  \n"
            "Demo accounts: `admin@lumiere-coffee.example.com` or `admin@helix-analytics.example.com`  \n"
            "Password: `DEMO_ADMIN_PASSWORD` from your `.env` (default: `demo-admin-2025`).  \n"
            "Run `make seed-demo-users` to create them."
        )
        with st.form("admin-login"):
            login_api_base = st.text_input("API base URL", value=default_api_base_url(), key="login_api_base")
            email = st.text_input("Email", key="login_email")
            password = st.text_input("Password", type="password", key="login_password")
            submitted = st.form_submit_button("Log in")

        if submitted and not email or submitted and not password:
            st.error("Please enter both email and password.")
        elif submitted:
            result = AdminAPI(login_api_base).post("/auth/login", {"email": email, "password": password})
            if result.ok and isinstance(result.data, dict):
                new_token = str(result.data.get("access_token", ""))
                persist_session(new_token, login_api_base, mode="admin")
                # Fetch and cache identity for the sidebar
                id_result = fetch_identity(login_api_base, new_token)
                if id_result.ok and isinstance(id_result.data, dict):
                    st.session_state["identity"] = id_result.data
                st.rerun()
            elif result.status_code == 401:
                st.error("Invalid email or password. Run `make seed-demo-users` if you have not created demo accounts yet.")
            elif result.status_code == 422:
                st.error("Invalid request format — check that email and password fields are filled in correctly.")
            else:
                st.error(error_message(result, route_name="Auth login"))

    # ── Tenant Token Login ────────────────────────────────────────────────────
    with token_tab:
        st.caption(
            "Paste an existing tenant admin bearer token to sign in.  \n"
            "The token is validated against the backend before access is granted."
        )
        with st.form("token-login"):
            token_api_base = st.text_input("API base URL", value=default_api_base_url(), key="token_api_base")
            pasted_token = st.text_input("Bearer token", type="password", key="pasted_token")
            validate_submitted = st.form_submit_button("Validate & sign in")

        if validate_submitted and not pasted_token:
            st.error("Please paste a bearer token before submitting.")
        elif validate_submitted:
            id_result = fetch_identity(token_api_base, pasted_token)
            if id_result.ok and isinstance(id_result.data, dict):
                persist_session(pasted_token, token_api_base, mode="token")
                st.session_state["identity"] = id_result.data
                st.rerun()
            elif id_result.status_code == 401:
                st.error("Invalid or expired token. Obtain a fresh token via Admin Login.")
            else:
                st.error(error_message(id_result, route_name="Token validation"))
