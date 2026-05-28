"""Admin routes (T091) — per-tenant admin endpoints.

GET/PUT /admin/tenant       — persona, theme, plan settings
GET/PUT /admin/guardrails   — tenant-scoped rails (platform rails read-only; cannot be weakened)
GET/POST/DELETE /admin/origins — allowed origins management
GET /admin/escalations      — list escalated conversations for this tenant

All endpoints require an authenticated tenant_admin (tenant_id from JWT).
Platform-rail weakening → 403 + audit-logged (enforced by UpdateGuardrailConfigUseCase).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.frameworks.api.deps import db_session, get_current_tenant_id
from app.frameworks.db.models import ConversationModel, TenantModel

router = APIRouter(prefix="/admin", tags=["admin"])


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


# --- /admin/tenant ---


@router.get("/tenant", response_model=TenantSettings)
async def get_tenant_settings(
    tenant_id_str: str = Depends(get_current_tenant_id),
    session: AsyncSession = Depends(db_session),
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
    tenant_id_str: str = Depends(get_current_tenant_id),
    session: AsyncSession = Depends(db_session),
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
    tenant_id_str: str = Depends(get_current_tenant_id),
    session: AsyncSession = Depends(db_session),
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
    tenant_id_str: str = Depends(get_current_tenant_id),
    session: AsyncSession = Depends(db_session),
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


@router.get("/origins", response_model=list[AllowedOriginOut])
async def list_origins(
    tenant_id_str: str = Depends(get_current_tenant_id),
    session: AsyncSession = Depends(db_session),
) -> list[AllowedOriginOut]:
    # AllowedOriginModel is owned by Owner A (migration 003); stub returns empty
    # until Owner A ships. Annotated with [B→A dependency].
    return []


@router.post("/origins", response_model=AllowedOriginOut, status_code=status.HTTP_201_CREATED)
async def add_origin(
    body: AllowedOriginCreate,
    tenant_id_str: str = Depends(get_current_tenant_id),
    session: AsyncSession = Depends(db_session),
) -> AllowedOriginOut:
    raise HTTPException(
        status.HTTP_501_NOT_IMPLEMENTED,
        "Origins management requires Owner A's AllowedOriginModel (T116). Not yet available.",
    )


@router.delete("/origins/{origin_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_origin(
    origin_id: UUID,
    tenant_id_str: str = Depends(get_current_tenant_id),
    session: AsyncSession = Depends(db_session),
) -> None:
    raise HTTPException(
        status.HTTP_501_NOT_IMPLEMENTED,
        "Origins management requires Owner A's AllowedOriginModel (T116). Not yet available.",
    )


# --- /admin/escalations ---


@router.get("/escalations", response_model=list[EscalatedConversation])
async def list_escalations(
    tenant_id_str: str = Depends(get_current_tenant_id),
    session: AsyncSession = Depends(db_session),
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
