"""Admin routes (T091) — per-tenant admin endpoints.

GET/PUT /admin/tenant       — persona, theme, plan settings
GET/PUT /admin/guardrails   — tenant-scoped rails (platform rails read-only; cannot be weakened)
GET/POST/DELETE /admin/origins — allowed origins management
GET /admin/widget           — widget public_id for embed snippet
GET /admin/escalations      — list escalated conversations for this tenant

All endpoints require an authenticated tenant_admin (tenant_id from JWT).
Platform-rail weakening → 403 + audit-logged (enforced by UpdateGuardrailConfigUseCase).
"""

from __future__ import annotations

import re
from collections.abc import AsyncIterator
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.entities.user import UserRole
from app.frameworks.api.session_auth import get_principal
from app.frameworks.db.models import (
    AllowedOriginModel,
    CMSPageModel,
    ConversationModel,
    LeadModel,
    MessageModel,
    TenantModel,
    WidgetModel,
)
from app.frameworks.db.session import get_session, reset_tenant_id, reset_user_id, set_tenant_id, set_user_id

router = APIRouter(prefix="/admin", tags=["admin"])


# --- Admin Tenant ID Dependency (from session token) ---


async def get_admin_tenant_id(principal=Depends(get_principal)) -> AsyncIterator[str]:
    """Validate the session token is tenant_admin, set RLS ContextVars, yield tenant_id.

    This MUST be a generator so that set_tenant_id() runs before admin_db_session
    creates the session and applies the app.tenant_id GUC via _apply_tenant_guc().
    The ContextVars are reset in the finally block to keep request isolation clean.
    """
    if principal.role is not UserRole.TENANT_ADMIN:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "tenant_admin role required")
    if principal.tenant_id is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Admin role requires tenant_id")
    tid_token = set_tenant_id(principal.tenant_id)
    uid_token = set_user_id(principal.user_id)
    try:
        yield principal.tenant_id
    finally:
        reset_tenant_id(tid_token)
        reset_user_id(uid_token)


async def admin_db_session(
    tenant_id_str: str = Depends(get_admin_tenant_id),
) -> AsyncIterator[AsyncSession]:
    """RLS-scoped DB session for admin routes.

    Depends on get_admin_tenant_id to guarantee the ContextVar is set before
    get_session() calls _apply_tenant_guc(). FastAPI resolves generator
    dependencies in dependency order, so the GUC is correctly applied.
    """
    async for s in get_session():
        yield s


# --- Schemas (per api.openapi.yaml) ---


class TenantSettings(BaseModel):
    id: UUID
    display_name: str
    slug: str
    plan: str
    persona_config: dict[str, Any] = {}
    theme_config: dict[str, Any] = {}


class TenantSettingsUpdate(BaseModel):
    display_name: str | None = None
    persona_config: dict[str, Any] | None = None
    theme_config: dict[str, Any] | None = None


class TenantGuardrailConfig(BaseModel):
    allowed_topics: list[str] = []
    blocked_topics: list[str] = []
    refusal_tone: str = "polite"
    enabled_tools: list[str] = ["rag_search", "capture_lead", "escalate"]


class AllowedOriginOut(BaseModel):
    id: UUID
    tenant_id: UUID
    origin: str


class AllowedOriginCreate(BaseModel):
    origin: str


class EscalatedConversation(BaseModel):
    conversation_id: UUID
    escalated_at: datetime | None = None
    escalation_reason: str | None = None


# --- /admin/analytics response models ---


class _IntentCount(BaseModel):
    intent: str
    count: int


class _DailyCount(BaseModel):
    date: str
    count: int


class _RouteCount(BaseModel):
    label: str
    count: int


class _ReasonCount(BaseModel):
    reason: str
    count: int


class _RecentLead(BaseModel):
    created_at: str | None
    name: str | None
    contact: str
    intent: str
    conversation_id: str


class _RecentEscalation(BaseModel):
    conversation_id: str
    escalated_at: str | None
    reason: str | None


class LeadAnalytics(BaseModel):
    total: int
    today: int
    this_week: int
    by_intent: list[_IntentCount]
    daily: list[_DailyCount]
    recent: list[_RecentLead]


class ConversationAnalytics(BaseModel):
    total: int
    escalated_open: int
    daily: list[_DailyCount]
    by_route: list[_RouteCount]


class EscalationAnalytics(BaseModel):
    total: int
    by_reason: list[_ReasonCount]
    recent: list[_RecentEscalation]


class CMSAnalytics(BaseModel):
    published: int
    draft: int
    unpublished: int


class WidgetAnalytics(BaseModel):
    is_enabled: bool
    allowed_origins: int


class DashboardAnalytics(BaseModel):
    leads: LeadAnalytics
    conversations: ConversationAnalytics
    escalations: EscalationAnalytics
    cms: CMSAnalytics
    widget: WidgetAnalytics


class WidgetInfoOut(BaseModel):
    """Public widget info for embed snippet (no secrets)."""

    widget_id: str
    is_enabled: bool


# --- /admin/tenant ---


@router.get("/tenant", response_model=TenantSettings)
async def get_tenant_settings(
    tenant_id_str: str = Depends(get_admin_tenant_id),
    session: AsyncSession = Depends(admin_db_session),
) -> TenantSettings:
    tenant_id = UUID(tenant_id_str)
    result = await session.execute(
        select(TenantModel).where(TenantModel.id == tenant_id)
    )
    row = result.scalar_one_or_none()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Tenant not found")
    return TenantSettings(
        id=row.id,
        display_name=row.display_name,
        slug=row.slug,
        plan=row.plan,
        persona_config=row.persona_config or {},
        theme_config=row.theme_config or {},
    )


@router.put("/tenant", response_model=TenantSettings)
async def update_tenant_settings(
    body: TenantSettingsUpdate,
    tenant_id_str: str = Depends(get_admin_tenant_id),
    session: AsyncSession = Depends(admin_db_session),
) -> TenantSettings:
    tenant_id = UUID(tenant_id_str)
    result = await session.execute(
        select(TenantModel).where(TenantModel.id == tenant_id)
    )
    row = result.scalar_one_or_none()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Tenant not found")

    if body.display_name is not None:
        row.display_name = body.display_name
    if body.persona_config is not None:
        row.persona_config = body.persona_config
    if body.theme_config is not None:
        row.theme_config = body.theme_config

    await session.flush()
    await session.refresh(row)
    return TenantSettings(
        id=row.id,
        display_name=row.display_name,
        slug=row.slug,
        plan=row.plan,
        persona_config=row.persona_config or {},
        theme_config=row.theme_config or {},
    )


# --- /admin/guardrails ---

_PLATFORM_RAILS = {"injection_defense", "jailbreak_defense", "cross_tenant_defense", "pii_redaction"}


@router.get("/guardrails", response_model=TenantGuardrailConfig)
async def get_guardrail_config(
    tenant_id_str: str = Depends(get_admin_tenant_id),
    session: AsyncSession = Depends(admin_db_session),
) -> TenantGuardrailConfig:
    tenant_id = UUID(tenant_id_str)
    result = await session.execute(
        select(TenantModel).where(TenantModel.id == tenant_id)
    )
    row = result.scalar_one_or_none()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Tenant not found")
    cfg = row.guardrail_config or {}
    return TenantGuardrailConfig(
        allowed_topics=cfg.get("allowed_topics", []),
        blocked_topics=cfg.get("blocked_topics", []),
        refusal_tone=cfg.get("refusal_tone", "polite"),
        enabled_tools=cfg.get("enabled_tools", ["rag_search", "capture_lead", "escalate"]),
    )


@router.put("/guardrails", response_model=TenantGuardrailConfig)
async def update_guardrail_config(
    body: TenantGuardrailConfig,
    tenant_id_str: str = Depends(get_admin_tenant_id),
    session: AsyncSession = Depends(admin_db_session),
) -> TenantGuardrailConfig:
    tenant_id = UUID(tenant_id_str)

    # Platform rails cannot be removed from enabled_tools (they're always on)
    disallowed = _PLATFORM_RAILS - set(body.enabled_tools)
    if disallowed:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            f"Cannot disable platform rails: {', '.join(sorted(disallowed))}",
        )

    result = await session.execute(
        select(TenantModel).where(TenantModel.id == tenant_id)
    )
    row = result.scalar_one_or_none()
    if row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Tenant not found")

    row.guardrail_config = {
        "allowed_topics": body.allowed_topics,
        "blocked_topics": body.blocked_topics,
        "refusal_tone": body.refusal_tone,
        "enabled_tools": body.enabled_tools,
    }
    await session.flush()
    return body


# --- /admin/origins ---


def _validate_origin_format(origin: str) -> bool:
    """Validate origin format: https?://host[:port]."""
    pattern = r"^https?://[a-zA-Z0-9._-]+(?:\.\w+)*(?::\d{2,5})?/?$"
    return bool(re.match(pattern, origin.strip()))


@router.get("/origins", response_model=list[AllowedOriginOut])
async def list_origins(
    tenant_id_str: str = Depends(get_admin_tenant_id),
    session: AsyncSession = Depends(admin_db_session),
) -> list[AllowedOriginOut]:
    """List all allowed origins for the current tenant."""
    tenant_id = UUID(tenant_id_str)
    result = await session.execute(
        select(AllowedOriginModel)
        .where(AllowedOriginModel.tenant_id == tenant_id)
        .order_by(AllowedOriginModel.created_at)
    )
    return [
        AllowedOriginOut(id=row.id, tenant_id=row.tenant_id, origin=row.origin)
        for row in result.scalars().all()
    ]


@router.post("/origins", response_model=AllowedOriginOut, status_code=status.HTTP_201_CREATED)
async def add_origin(
    body: AllowedOriginCreate,
    tenant_id_str: str = Depends(get_admin_tenant_id),
    session: AsyncSession = Depends(admin_db_session),
) -> AllowedOriginOut:
    """Add a new allowed origin for the current tenant.
    
    Validates:
    - Origin format (https?://host[:port])
    - No duplicates per tenant
    - Tenant-scoped isolation
    """
    tenant_id = UUID(tenant_id_str)
    origin = body.origin.strip()

    # Validate origin format
    if not _validate_origin_format(origin):
        raise HTTPException(
            status.HTTP_400_BAD_REQUEST,
            "Invalid origin format. Use https://host[:port] or http://host[:port]",
        )

    # Check for duplicates within this tenant
    existing = await session.execute(
        select(AllowedOriginModel).where(
            AllowedOriginModel.tenant_id == tenant_id,
            AllowedOriginModel.origin == origin,
        )
    )
    if existing.scalar_one_or_none() is not None:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            f"Origin already allowed for this tenant: {origin}",
        )

    # Create new origin record
    new_origin = AllowedOriginModel(
        tenant_id=tenant_id,
        origin=origin,
    )
    session.add(new_origin)
    await session.flush()
    await session.refresh(new_origin)

    return AllowedOriginOut(
        id=new_origin.id,
        tenant_id=new_origin.tenant_id,
        origin=new_origin.origin,
    )


@router.delete("/origins/{origin_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_origin(
    origin_id: UUID,
    tenant_id_str: str = Depends(get_admin_tenant_id),
    session: AsyncSession = Depends(admin_db_session),
) -> None:
    """Delete an allowed origin. Enforces tenant isolation."""
    tenant_id = UUID(tenant_id_str)

    # Find and verify ownership
    result = await session.execute(
        select(AllowedOriginModel).where(AllowedOriginModel.id == origin_id)
    )
    origin_row = result.scalar_one_or_none()
    if origin_row is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Origin not found")

    # Verify tenant ownership
    if origin_row.tenant_id != tenant_id:
        raise HTTPException(
            status.HTTP_403_FORBIDDEN,
            "Cannot delete an origin owned by another tenant",
        )

    await session.delete(origin_row)
    await session.flush()


# --- /admin/widget ---


@router.get("/widget", response_model=WidgetInfoOut)
async def get_widget_info(
    tenant_id_str: str = Depends(get_admin_tenant_id),
    session: AsyncSession = Depends(admin_db_session),
) -> WidgetInfoOut:
    """Get widget info (public_id) for the current tenant.
    
    Used by the embed snippet page to auto-populate the widget ID.
    Does not expose secrets or internal service tokens.
    """
    tenant_id = UUID(tenant_id_str)
    result = await session.execute(
        select(WidgetModel).where(WidgetModel.tenant_id == tenant_id)
    )
    widget_row = result.scalar_one_or_none()
    if widget_row is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND,
            "No widget provisioned for this tenant",
        )

    return WidgetInfoOut(
        widget_id=widget_row.public_id,
        is_enabled=widget_row.is_enabled,
    )


# --- /admin/escalations ---


@router.get("/escalations", response_model=list[EscalatedConversation])
async def list_escalations(
    tenant_id_str: str = Depends(get_admin_tenant_id),
    session: AsyncSession = Depends(admin_db_session),
) -> list[EscalatedConversation]:
    tenant_id = UUID(tenant_id_str)
    result = await session.execute(
        select(ConversationModel)
        .where(
            ConversationModel.tenant_id == tenant_id,
            ConversationModel.escalated_at.isnot(None),
        )
        .order_by(ConversationModel.escalated_at.desc())
    )
    return [
        EscalatedConversation(
            conversation_id=row.id,
            escalated_at=row.escalated_at,
            escalation_reason=row.escalation_reason,
        )
        for row in result.scalars().all()
    ]


# --- /admin/analytics ---


@router.get("/analytics", response_model=DashboardAnalytics)
async def get_analytics(
    tenant_id_str: str = Depends(get_admin_tenant_id),
    session: AsyncSession = Depends(admin_db_session),
) -> DashboardAnalytics:
    """Tenant-scoped aggregate analytics for the admin dashboard."""
    tenant_id = UUID(tenant_id_str)
    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    week_start = now - timedelta(days=7)
    fourteen_ago = now - timedelta(days=14)

    # ── Leads ─────────────────────────────────────────────────────────────────
    leads_total = await session.scalar(
        select(func.count()).select_from(LeadModel).where(LeadModel.tenant_id == tenant_id)
    ) or 0
    leads_today = await session.scalar(
        select(func.count()).select_from(LeadModel).where(
            LeadModel.tenant_id == tenant_id,
            LeadModel.created_at >= today_start,
        )
    ) or 0
    leads_week = await session.scalar(
        select(func.count()).select_from(LeadModel).where(
            LeadModel.tenant_id == tenant_id,
            LeadModel.created_at >= week_start,
        )
    ) or 0
    intent_rows = (await session.execute(
        select(LeadModel.intent, func.count().label("cnt"))
        .where(LeadModel.tenant_id == tenant_id)
        .group_by(LeadModel.intent)
        .order_by(func.count().desc())
    )).all()
    daily_leads_rows = (await session.execute(
        select(func.date(LeadModel.created_at).label("day"), func.count().label("cnt"))
        .where(LeadModel.tenant_id == tenant_id, LeadModel.created_at >= fourteen_ago)
        .group_by(func.date(LeadModel.created_at))
        .order_by(func.date(LeadModel.created_at))
    )).all()
    recent_lead_rows = (await session.execute(
        select(LeadModel)
        .where(LeadModel.tenant_id == tenant_id)
        .order_by(LeadModel.created_at.desc())
        .limit(5)
    )).scalars().all()

    # ── Conversations ─────────────────────────────────────────────────────────
    conv_total = await session.scalar(
        select(func.count()).select_from(ConversationModel).where(ConversationModel.tenant_id == tenant_id)
    ) or 0
    conv_escalated = await session.scalar(
        select(func.count()).select_from(ConversationModel).where(
            ConversationModel.tenant_id == tenant_id,
            ConversationModel.escalated_at.isnot(None),
        )
    ) or 0
    daily_conv_rows = (await session.execute(
        select(func.date(ConversationModel.started_at).label("day"), func.count().label("cnt"))
        .where(ConversationModel.tenant_id == tenant_id, ConversationModel.started_at >= fourteen_ago)
        .group_by(func.date(ConversationModel.started_at))
        .order_by(func.date(ConversationModel.started_at))
    )).all()
    route_rows = (await session.execute(
        select(MessageModel.router_label, func.count().label("cnt"))
        .where(MessageModel.tenant_id == tenant_id, MessageModel.router_label.isnot(None))
        .group_by(MessageModel.router_label)
        .order_by(func.count().desc())
    )).all()

    # ── Escalations ──────────────────────────────────────────────────────────
    reason_rows = (await session.execute(
        select(ConversationModel.escalation_reason, func.count().label("cnt"))
        .where(ConversationModel.tenant_id == tenant_id, ConversationModel.escalated_at.isnot(None))
        .group_by(ConversationModel.escalation_reason)
    )).all()
    recent_esc_rows = (await session.execute(
        select(ConversationModel)
        .where(ConversationModel.tenant_id == tenant_id, ConversationModel.escalated_at.isnot(None))
        .order_by(ConversationModel.escalated_at.desc())
        .limit(5)
    )).scalars().all()

    # ── CMS ──────────────────────────────────────────────────────────────────
    cms_rows = (await session.execute(
        select(CMSPageModel.state, func.count().label("cnt"))
        .where(CMSPageModel.tenant_id == tenant_id)
        .group_by(CMSPageModel.state)
    )).all()
    cms_counts = {r.state: r.cnt for r in cms_rows}

    # ── Widget & Origins ─────────────────────────────────────────────────────
    widget_row = (await session.execute(
        select(WidgetModel).where(WidgetModel.tenant_id == tenant_id)
    )).scalar_one_or_none()
    origins_count = await session.scalar(
        select(func.count()).select_from(AllowedOriginModel).where(AllowedOriginModel.tenant_id == tenant_id)
    ) or 0

    return DashboardAnalytics(
        leads=LeadAnalytics(
            total=leads_total,
            today=leads_today,
            this_week=leads_week,
            by_intent=[_IntentCount(intent=r.intent, count=r.cnt) for r in intent_rows],
            daily=[_DailyCount(date=str(r.day), count=r.cnt) for r in daily_leads_rows],
            recent=[
                _RecentLead(
                    created_at=row.created_at.isoformat() if row.created_at else None,
                    name=row.name,
                    contact=row.contact,
                    intent=row.intent,
                    conversation_id=str(row.conversation_id),
                )
                for row in recent_lead_rows
            ],
        ),
        conversations=ConversationAnalytics(
            total=conv_total,
            escalated_open=conv_escalated,
            daily=[_DailyCount(date=str(r.day), count=r.cnt) for r in daily_conv_rows],
            by_route=[_RouteCount(label=r.router_label, count=r.cnt) for r in route_rows],
        ),
        escalations=EscalationAnalytics(
            total=conv_escalated,
            by_reason=[_ReasonCount(reason=r.escalation_reason or "unknown", count=r.cnt) for r in reason_rows],
            recent=[
                _RecentEscalation(
                    conversation_id=str(row.id),
                    escalated_at=row.escalated_at.isoformat() if row.escalated_at else None,
                    reason=row.escalation_reason,
                )
                for row in recent_esc_rows
            ],
        ),
        cms=CMSAnalytics(
            published=cms_counts.get("published", 0),
            draft=cms_counts.get("draft", 0),
            unpublished=cms_counts.get("unpublished", 0),
        ),
        widget=WidgetAnalytics(
            is_enabled=widget_row.is_enabled if widget_row else False,
            allowed_origins=origins_count,
        ),
    )
