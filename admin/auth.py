"""Shared admin auth helpers.

Handles cookie-backed session persistence so login survives browser refresh.
Call restore_session() at the top of every page before reading session state.
Call require_auth() on protected pages — it restores, validates, and stops if
the visitor is not authenticated.

The token lives in a browser cookie (COOKIE_NAME). It is never logged.
"""

from __future__ import annotations

import streamlit as st
import streamlit.components.v1 as components

from api_client import AdminAPI, APIResult
from config import default_api_base_url

COOKIE_NAME = "concierge_admin_token"
# Align with the 12-hour session TTL issued by /auth/login.
_COOKIE_MAX_AGE = 12 * 60 * 60  # seconds


def _write_cookie(name: str, value: str, max_age: int) -> None:
    # Embed JS directly via srcdoc — no network round-trip, executes immediately.
    # JWTs are base64url (A-Za-z0-9-_.) so embedding in a JS string is safe.
    components.html(
        f'<script>document.cookie="{name}={value};max-age={max_age};path=/;SameSite=Lax";</script>',
        height=0,
    )


def _erase_cookie(name: str) -> None:
    components.html(
        f'<script>document.cookie="{name}=;max-age=0;path=/;SameSite=Lax";</script>',
        height=0,
    )


def restore_session() -> None:
    """Populate st.session_state from the HTTP-header cookie if not already set.

    st.context.cookies is read-only and backed by the incoming HTTP request —
    no JavaScript round-trip required. Skips restoration after an explicit
    logout so the stale cookie does not re-log the user in before the browser
    processes the JS erase.
    """
    if st.session_state.get("access_token"):
        return
    if st.session_state.get("_logged_out"):
        return
    token = st.context.cookies.get(COOKIE_NAME)
    if token:
        st.session_state["access_token"] = token
        if not st.session_state.get("api_base"):
            st.session_state["api_base"] = default_api_base_url()


def persist_session(token: str, api_base: str, mode: str) -> None:
    """Write the token to both session state and the browser cookie."""
    st.session_state["access_token"] = token
    st.session_state["api_base"] = api_base.rstrip("/")
    st.session_state["auth_mode"] = mode
    _write_cookie(COOKIE_NAME, token, _COOKIE_MAX_AGE)


def clear_session() -> None:
    """Remove the token from session state and expire the browser cookie."""
    for key in ("access_token", "api_base", "auth_mode", "identity"):
        st.session_state.pop(key, None)
    st.session_state["_logged_out"] = True
    _erase_cookie(COOKIE_NAME)


def fetch_identity(api_base: str, token: str) -> APIResult:
    """Call GET /auth/me and return the result (does not modify session state)."""
    return AdminAPI(api_base.rstrip("/"), token).get("/auth/me")


def require_auth() -> tuple[str, str]:
    """Restore session from cookie, then gate on a valid token.

    Renders the identity + Logout button in the sidebar.
    Calls st.stop() if unauthenticated so the rest of the page never runs.
    Returns (api_base, token) for the caller to use.
    """
    restore_session()
    token: str = st.session_state.get("access_token", "")
    api_base: str = st.session_state.get("api_base", default_api_base_url())

    if not token:
        st.info("Please sign in on the main page.")
        st.stop()

    _render_sidebar(api_base, token)
    return api_base, token


def _render_sidebar(api_base: str, token: str) -> None:
    identity = st.session_state.get("identity")
    with st.sidebar:
        if identity:
            st.caption(
                f"**{identity.get('email', '')}**  \n"
                f"Role: {identity.get('role', '')}  \n"
                f"Tenant: {identity.get('tenant_id', 'n/a')}"
            )
        if st.button("Logout", key="sidebar_logout"):
            clear_session()
            st.rerun()
