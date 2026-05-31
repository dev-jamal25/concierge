import json

import streamlit as st

from api_client import AdminAPI, error_message
from auth import require_auth

st.title("Settings")

api_base, token = require_auth()

api = AdminAPI(api_base, token)


def _json_text(value: object) -> str:
    return json.dumps(value or {}, indent=2, sort_keys=True)


def _lines(value: list[str]) -> str:
    return "\n".join(value)


def _split_lines(value: str) -> list[str]:
    return [line.strip() for line in value.splitlines() if line.strip()]


tenant_result = api.get("/admin/tenant")
if tenant_result.route_missing:
    st.warning(error_message(tenant_result, route_name="Tenant settings"))
    st.stop()
if not tenant_result.ok or not isinstance(tenant_result.data, dict):
    st.error(error_message(tenant_result, route_name="Tenant settings"))
    st.stop()

tenant = tenant_result.data
persona_config = tenant.get("persona_config") or {}
theme_config = tenant.get("theme_config") or {}

st.subheader("Tenant and Widget Config")
st.caption("Widget greeting and consent notice are stored in tenant theme config.")
with st.form("tenant-settings"):
    display_name = st.text_input("Display name", value=tenant.get("display_name", ""))
    greeting = st.text_input(
        "Widget greeting",
        value=str(theme_config.get("greeting", "Hi, how can I help?")),
    )
    consent_notice = st.text_area(
        "Widget consent notice",
        value=str(
            theme_config.get(
                "consent_notice",
                "By chatting, you agree to share this conversation with the site owner.",
            )
        ),
    )
    persona_summary = st.text_area(
        "Persona summary",
        value=str(persona_config.get("summary", "")),
    )
    theme_json = st.text_area("Theme JSON", value=_json_text(theme_config), height=180)
    persona_json = st.text_area("Persona JSON", value=_json_text(persona_config), height=180)
    save_tenant = st.form_submit_button("Save tenant/widget settings")

if save_tenant:
    try:
        next_theme = json.loads(theme_json or "{}")
        next_persona = json.loads(persona_json or "{}")
    except json.JSONDecodeError as exc:
        st.error(f"Invalid JSON: {exc}")
    else:
        next_theme["greeting"] = greeting
        next_theme["consent_notice"] = consent_notice
        next_persona["summary"] = persona_summary
        result = api.put(
            "/admin/tenant",
            {
                "display_name": display_name,
                "theme_config": next_theme,
                "persona_config": next_persona,
            },
        )
        if result.ok:
            st.success("Tenant/widget settings saved.")
        else:
            st.error(error_message(result, route_name="Tenant settings"))

st.subheader("Guardrails")
guardrails_result = api.get("/admin/guardrails")
if guardrails_result.route_missing:
    st.warning(error_message(guardrails_result, route_name="Guardrail settings"))
elif not guardrails_result.ok or not isinstance(guardrails_result.data, dict):
    st.error(error_message(guardrails_result, route_name="Guardrail settings"))
else:
    guardrails = guardrails_result.data
    platform_rails = [
        "injection_defense",
        "jailbreak_defense",
        "cross_tenant_defense",
        "pii_redaction",
    ]
    business_tools = ["rag_search", "capture_lead", "escalate"]
    current_enabled = set(guardrails.get("enabled_tools", []))

    st.caption("Platform rails are locked on and cannot be disabled.")
    st.dataframe(
        [{"platform_rail": rail, "status": "locked on"} for rail in platform_rails],
        use_container_width=True,
        hide_index=True,
    )
    with st.form("guardrail-settings"):
        allowed_topics = st.text_area(
            "Allowed topics",
            value=_lines(guardrails.get("allowed_topics", [])),
        )
        blocked_topics = st.text_area(
            "Blocked topics",
            value=_lines(guardrails.get("blocked_topics", [])),
        )
        refusal_tone = st.text_input(
            "Refusal tone",
            value=str(guardrails.get("refusal_tone", "polite")),
        )
        enabled_tools = st.multiselect(
            "Tenant tools enabled for the agent",
            options=business_tools,
            default=[tool for tool in business_tools if tool in current_enabled or not current_enabled],
        )
        save_guardrails = st.form_submit_button("Save guardrail settings")

    if save_guardrails:
        result = api.put(
            "/admin/guardrails",
            {
                "allowed_topics": _split_lines(allowed_topics),
                "blocked_topics": _split_lines(blocked_topics),
                "refusal_tone": refusal_tone,
                "enabled_tools": platform_rails + enabled_tools,
            },
        )
        if result.ok:
            st.success("Guardrail settings saved.")
        else:
            st.error(error_message(result, route_name="Guardrail settings"))

st.subheader("Allowed Origins")
origins_result = api.get("/admin/origins")
if origins_result.route_missing:
    st.warning(error_message(origins_result, route_name="Allowed origins"))
elif not origins_result.ok:
    st.error(error_message(origins_result, route_name="Allowed origins"))
else:
    origins = origins_result.data if isinstance(origins_result.data, list) else []
    if origins:
        st.dataframe(origins, use_container_width=True, hide_index=True)
    else:
        st.info("No origins returned by the backend for this tenant.")

    new_origin = st.text_input("Add origin", placeholder="https://example.com")
    if st.button("Add origin", disabled=not new_origin):
        result = api.post("/admin/origins", {"origin": new_origin})
        if result.ok:
            st.success("Origin added.")
        else:
            st.error(error_message(result, route_name="Add origin"))

    if origins:
        origin_by_label = {origin["origin"]: origin for origin in origins if "id" in origin}
        selected_origin = st.selectbox("Origin to delete", list(origin_by_label.keys()))
        if st.button("Delete selected origin"):
            result = api.delete(f"/admin/origins/{origin_by_label[selected_origin]['id']}")
            if result.ok:
                st.success("Origin deleted.")
            else:
                st.error(error_message(result, route_name="Delete origin"))
