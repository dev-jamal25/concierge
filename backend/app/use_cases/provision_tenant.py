"""ProvisionTenantUseCase (T108).

Creates the tenant, its widget row, seeds allowed origins, invites the first
admin, and audit-logs the action. Depends only on protocols (Clean Architecture);
the composition root injects concrete adapters.
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from uuid import UUID

from app.entities.audit_entry import AuditOutcome
from app.entities.tenant import Tenant
from app.use_cases.invite_admin import InviteAdminUseCase
from app.use_cases.protocols.audit_repository import AuditRepository
from app.use_cases.protocols.tenant_repository import TenantRepository


@dataclass(slots=True)
class ProvisionResult:
    tenant: Tenant
    widget_public_id: str
    invitation_token: str


class ProvisionTenantUseCase:
    def __init__(
        self,
        tenants: TenantRepository,
        audit: AuditRepository,
        invite_admin: InviteAdminUseCase,
    ) -> None:
        self._tenants = tenants
        self._audit = audit
        self._invite_admin = invite_admin

    async def execute(
        self,
        *,
        slug: str,
        display_name: str,
        admin_email: str,
        allowed_origins: list[str],
        actor_user_id: UUID,
        plan: str = "poc",
        persona_config: dict | None = None,
        theme_config: dict | None = None,
        guardrail_config: dict | None = None,
    ) -> ProvisionResult:
        tenant = await self._tenants.create(
            slug=slug,
            display_name=display_name,
            plan=plan,
            persona_config=persona_config,
            theme_config=theme_config,
            guardrail_config=guardrail_config,
        )

        widget_public_id = secrets.token_urlsafe(16)
        await self._tenants.create_widget(tenant.id, widget_public_id)

        for origin in allowed_origins:
            await self._tenants.add_allowed_origin(tenant.id, origin)

        invite = await self._invite_admin.execute(
            tenant_id=tenant.id,
            tenant_name=tenant.display_name,
            email=admin_email,
            created_by=actor_user_id,
        )

        await self._audit.log(
            action="tenant_create",
            outcome=AuditOutcome.SUCCESS,
            actor_user_id=actor_user_id,
            target_tenant_id=tenant.id,
            details={"slug": slug, "admin_email": admin_email, "origins": allowed_origins},
        )

        return ProvisionResult(
            tenant=tenant,
            widget_public_id=widget_public_id,
            invitation_token=invite.raw_token,
        )
