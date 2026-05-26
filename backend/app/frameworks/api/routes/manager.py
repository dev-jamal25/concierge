"""Manager routes (T115) — tenant_manager only.

POST /manager/tenants    → provision a tenant (201 TenantSummary)
GET  /manager/tenants    → list all tenants (metadata only)
DELETE /manager/tenants/{id} → async erase (202)
GET  /manager/audit      → append-only audit log
GET  /manager/usage      → aggregate usage (no per-tenant content)

All run under the concierge_manager session, whose grants are limited to tenants
+ audit_entries + provisioning tables — never visitor content (correction #2).
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Response, status
from pydantic import BaseModel, EmailStr
from sqlalchemy import func, select

from app.frameworks.api.deps import ManagerContext, get_manager_context
from app.frameworks.api.session_auth import Principal, require_manager
from app.frameworks.db.models import TenantModel

router = APIRouter(prefix="/manager", tags=["manager"])


class TenantSummary(BaseModel):
    id: UUID
    display_name: str
    slug: str
    plan: str
    status: str
    created_at: datetime | None = None


class ProvisionTenantRequest(BaseModel):
    display_name: str
    slug: str
    first_admin_email: EmailStr
    seed_allowed_origins: list[str] = []


class AuditEntryOut(BaseModel):
    id: UUID
    actor_user_id: UUID | None = None
    target_tenant_id: UUID | None = None
    action: str
    outcome: str
    details: dict = {}
    created_at: datetime | None = None


class UsageAggregate(BaseModel):
    tenant_count: int
    active_tenant_count: int
    total_conversations_30d: int = 0
    total_leads_30d: int = 0
    total_llm_input_tokens_30d: int = 0
    total_llm_output_tokens_30d: int = 0
    total_embedding_tokens_30d: int = 0


@router.get("/tenants", response_model=list[TenantSummary])
async def list_tenants(
    _: Principal = Depends(require_manager),
    ctx: ManagerContext = Depends(get_manager_context),
) -> list[TenantSummary]:
    tenants = await ctx.tenants.list()
    return [
        TenantSummary(
            id=t.id,
            display_name=t.display_name,
            slug=t.slug,
            plan=t.plan.value,
            status=t.status.value,
            created_at=t.created_at,
        )
        for t in tenants
    ]


@router.post("/tenants", response_model=TenantSummary, status_code=status.HTTP_201_CREATED)
async def provision_tenant(
    body: ProvisionTenantRequest,
    principal: Principal = Depends(require_manager),
    ctx: ManagerContext = Depends(get_manager_context),
) -> TenantSummary:
    result = await ctx.provision.execute(
        slug=body.slug,
        display_name=body.display_name,
        admin_email=body.first_admin_email,
        allowed_origins=body.seed_allowed_origins,
        actor_user_id=UUID(principal.user_id),
    )
    t = result.tenant
    return TenantSummary(
        id=t.id,
        display_name=t.display_name,
        slug=t.slug,
        plan=t.plan.value,
        status=t.status.value,
        created_at=t.created_at,
    )


@router.delete("/tenants/{tenant_id}", status_code=status.HTTP_202_ACCEPTED)
async def erase_tenant(
    tenant_id: UUID,
    principal: Principal = Depends(require_manager),
    ctx: ManagerContext = Depends(get_manager_context),
) -> Response:
    # PoC: erasure runs synchronously within the SLA, returns 202 per the contract.
    await ctx.erase.execute(tenant_id=tenant_id, actor_user_id=UUID(principal.user_id))
    return Response(status_code=status.HTTP_202_ACCEPTED)


@router.get("/audit", response_model=list[AuditEntryOut])
async def read_audit(
    _: Principal = Depends(require_manager),
    ctx: ManagerContext = Depends(get_manager_context),
    target_tenant_id: UUID | None = None,
    since: datetime | None = None,
) -> list[AuditEntryOut]:
    entries = await ctx.audit.list_all()
    out = []
    for e in entries:
        if target_tenant_id is not None and e.target_tenant_id != target_tenant_id:
            continue
        if since is not None and e.created_at is not None and e.created_at < since:
            continue
        out.append(
            AuditEntryOut(
                id=e.id,
                actor_user_id=e.actor_user_id,
                target_tenant_id=e.target_tenant_id,
                action=e.action,
                outcome=e.outcome.value,
                details=e.details,
                created_at=e.created_at,
            )
        )
    return out


@router.get("/usage", response_model=UsageAggregate)
async def read_usage(
    _: Principal = Depends(require_manager),
    ctx: ManagerContext = Depends(get_manager_context),
) -> UsageAggregate:
    # Aggregate only — derived from tenant metadata. Content-derived metrics
    # (conversations/leads/tokens) are owned by Owner B's tables and remain 0
    # here until that surface lands; the manager role cannot read content.
    total = (await ctx.session.execute(select(func.count()).select_from(TenantModel))).scalar_one()
    active = (
        await ctx.session.execute(
            select(func.count()).select_from(TenantModel).where(TenantModel.status == "active")
        )
    ).scalar_one()
    return UsageAggregate(tenant_count=int(total), active_tenant_count=int(active))
