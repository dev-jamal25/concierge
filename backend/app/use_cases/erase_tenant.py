"""EraseTenantUseCase (T110 — Postgres-store core).

Sets the tenant to 'erasing', cascade-deletes all Postgres rows (which also
removes the pgvector chunks, since they live in Postgres), and audit-logs
completion.

DEFERRED (T129 — cross-owner seam): the Redis key purge and MinIO prefix purge
require the SessionStore (T029, Owner B) and ObjectStorage (T031, Owner D)
protocols, which are not yet published. Per the ownership rules we do NOT stub
those here; when the protocols land, inject them and extend `execute()` to purge
those stores before writing the completion audit entry (stores_purged list grows
to ['pg','vector','redis','minio']).
"""

from __future__ import annotations

from uuid import UUID

from app.entities.audit_entry import AuditOutcome
from app.entities.tenant import TenantStatus
from app.use_cases.protocols.audit_repository import AuditRepository
from app.use_cases.protocols.tenant_repository import TenantRepository


class EraseTenantUseCase:
    def __init__(self, tenants: TenantRepository, audit: AuditRepository) -> None:
        self._tenants = tenants
        self._audit = audit

    async def execute(self, *, tenant_id: UUID, actor_user_id: UUID) -> None:
        await self._tenants.set_status(tenant_id, TenantStatus.ERASING)

        # Postgres cascade — removes cms_pages, chunks (pgvector), conversations,
        # messages, leads, widgets, allowed_origins, user_tenant_roles, invitations.
        await self._tenants.delete(tenant_id)

        await self._audit.log(
            action="tenant_erase_complete",
            outcome=AuditOutcome.SUCCESS,
            actor_user_id=actor_user_id,
            target_tenant_id=tenant_id,
            details={"stores_purged": ["pg", "vector"]},
        )
