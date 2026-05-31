"""Admin Dashboard — business-facing analytics for the current tenant."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from api_client import AdminAPI, error_message
from auth import require_auth

st.set_page_config(page_title="Dashboard — Concierge Admin", layout="wide")

api_base, token = require_auth()
api = AdminAPI(api_base, token)

st.title("Dashboard")

# ── Fetch analytics ───────────────────────────────────────────────────────────
with st.spinner("Loading analytics…"):
    analytics_result = api.get("/admin/analytics")

if not analytics_result.ok:
    if analytics_result.route_missing:
        # Graceful fallback: backend not yet updated — show legacy counts
        st.warning("Analytics endpoint not available. Showing basic summary.")
        tenant_result = api.get("/admin/tenant")
        cms_result = api.get("/cms/pages")
        leads_result = api.get("/leads")
        escalations_result = api.get("/admin/escalations")
        cols = st.columns(4)
        if tenant_result.ok and isinstance(tenant_result.data, dict):
            cols[0].metric("Tenant", tenant_result.data.get("display_name", "—"))
            cols[1].metric("Plan", tenant_result.data.get("plan", "—"))
        cols[2].metric("CMS Pages",
            len(cms_result.data) if cms_result.ok and isinstance(cms_result.data, list) else "n/a")
        cols[3].metric("Leads",
            len(leads_result.data) if leads_result.ok and isinstance(leads_result.data, list) else "n/a")
        st.stop()
    else:
        st.error(error_message(analytics_result, route_name="Analytics"))
        st.stop()

if not isinstance(analytics_result.data, dict):
    st.error("Unexpected analytics response format.")
    st.stop()

data = analytics_result.data
leads = data.get("leads", {})
convs = data.get("conversations", {})
escs = data.get("escalations", {})
cms = data.get("cms", {})
widget = data.get("widget", {})

# ── KPI row ───────────────────────────────────────────────────────────────────
st.subheader("Overview")
k1, k2, k3, k4, k5, k6 = st.columns(6)
k1.metric("Total Leads", leads.get("total", 0))
k2.metric("New Today", leads.get("today", 0))
k3.metric("New This Week", leads.get("this_week", 0))
k4.metric("Open Escalations", escs.get("total", 0))
k5.metric("Conversations", convs.get("total", 0))
k6.metric("CMS Published", cms.get("published", 0))

st.divider()

# ── Activity Trends ───────────────────────────────────────────────────────────
st.subheader("Activity — Last 14 Days")
t_left, t_right = st.columns(2)

with t_left:
    st.caption("**Leads per day**")
    leads_daily = leads.get("daily", [])
    if leads_daily:
        df_leads = (
            pd.DataFrame(leads_daily)
            .rename(columns={"date": "Date", "count": "Leads"})
            .set_index("Date")
        )
        st.area_chart(df_leads, color="#6B3A2A")
    else:
        st.info("No lead activity yet.")

with t_right:
    st.caption("**Conversations per day**")
    conv_daily = convs.get("daily", [])
    if conv_daily:
        df_conv = (
            pd.DataFrame(conv_daily)
            .rename(columns={"date": "Date", "count": "Conversations"})
            .set_index("Date")
        )
        st.area_chart(df_conv, color="#1A3A6B")
    else:
        st.info("No conversation activity yet.")

st.divider()

# ── Intent & Lead Breakdown ───────────────────────────────────────────────────
st.subheader("Message & Lead Breakdown")
b_left, b_right = st.columns(2)

with b_left:
    st.caption("**Conversations by intent**")
    by_route = convs.get("by_route", [])
    if by_route:
        df_route = (
            pd.DataFrame(by_route)
            .rename(columns={"label": "Intent", "count": "Count"})
            .set_index("Intent")
        )
        st.bar_chart(df_route)
    else:
        st.info("No message routing data yet.")

with b_right:
    st.caption("**Leads by intent**")
    by_intent = leads.get("by_intent", [])
    if by_intent:
        df_intent = (
            pd.DataFrame(by_intent)
            .rename(columns={"intent": "Intent", "count": "Count"})
            .set_index("Intent")
        )
        st.bar_chart(df_intent)
    else:
        st.info("No leads captured yet.")

st.divider()

# ── CMS & Widget Status ───────────────────────────────────────────────────────
st.subheader("Content & Widget")
c_left, c_right = st.columns(2)

with c_left:
    st.caption("**CMS pages by state**")
    cms_rows = [
        {"State": "Published", "Count": cms.get("published", 0)},
        {"State": "Draft",     "Count": cms.get("draft", 0)},
        {"State": "Unpublished", "Count": cms.get("unpublished", 0)},
    ]
    df_cms = pd.DataFrame(cms_rows).set_index("State")
    st.bar_chart(df_cms)

with c_right:
    st.caption("**Widget & origins**")
    w1, w2 = st.columns(2)
    w1.metric("Widget", "Enabled ✓" if widget.get("is_enabled") else "Disabled ✗")
    w2.metric("Allowed Origins", widget.get("allowed_origins", 0))

    esc_by_reason = escs.get("by_reason", [])
    if esc_by_reason:
        st.caption("**Escalations by reason**")
        df_esc = (
            pd.DataFrame(esc_by_reason)
            .rename(columns={"reason": "Reason", "count": "Count"})
            .set_index("Reason")
        )
        st.bar_chart(df_esc)

st.divider()

# ── Recent Activity ───────────────────────────────────────────────────────────
st.subheader("Recent Activity")
r_left, r_right = st.columns(2)

with r_left:
    st.caption("**Recent leads**")
    recent_leads = leads.get("recent", [])
    if recent_leads:
        st.dataframe(
            [
                {
                    "Time": (rl.get("created_at") or "")[:16].replace("T", " "),
                    "Name": rl.get("name") or "—",
                    "Contact": rl.get("contact", ""),
                    "Intent": rl.get("intent", ""),
                }
                for rl in recent_leads
            ],
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.info("No leads captured yet.")

with r_right:
    st.caption("**Recent escalations**")
    recent_escs = escs.get("recent", [])
    if recent_escs:
        st.dataframe(
            [
                {
                    "Time": (re.get("escalated_at") or "")[:16].replace("T", " "),
                    "Reason": re.get("reason") or "—",
                    "Conversation": (re.get("conversation_id") or "")[:8] + "…",
                }
                for re in recent_escs
            ],
            use_container_width=True,
            hide_index=True,
        )
    else:
        st.info("No escalations yet.")
