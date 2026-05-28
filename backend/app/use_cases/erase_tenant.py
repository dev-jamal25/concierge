"""EraseTenantUseCase (T110 — Postgres-store core, T129 — Redis seam).

Sets the tenant to 'erasing', cascade-deletes all Postgres rows (which also
removes the pgvector chunks, since they live in Postgres), purges Redis session
keys via the SessionStore protocol, and audit-logs completion.

SessionStore protocol (T029/T191, Owner B) is now published and injected as a
required constructor parameter. The concrete RedisSession adapter is wired in
deps.py (Owner A composition root) and must not be imported here.

DEFERRED (T031/T050, Owner D): MinIO prefix purge via ObjectStorage.delete_prefix
is not yet implemented. When Owner D delivers the ObjectStorage adapter, inject it
and extend `execute()` so stores_purged grows to ['pg', 'vector', 'redis', 'minio'].
"""

from __future__ import annotations

from uuid import UUID

from app.entities.audit_entry import AuditOutcome
from app.entities.tenant import TenantStatus
from app.use_cases.protocols.audit_repository import AuditRepository
from app.use_cases.protocols.session_store import SessionStore
from app.use_cases.protocols.tenant_repository import TenantRepository


class EraseTenantUseCase:
    def __init__(
        self,
        tenants: TenantRepository,
        audit: AuditRepository,
        session_store: SessionStore,
    ) -> None:
        self._tenants = tenants
        self._audit = audit
        self._session_store = session_store

    async def execute(self, *, tenant_id: UUID, actor_user_id: UUID) -> None:
        # 1. Write erase-start audit entry BEFORE mutating state (T129 auditor fix).
        await self._audit.log(
            action="tenant_erase_start",
            outcome=AuditOutcome.SUCCESS,
            actor_user_id=actor_user_id,
            target_tenant_id=tenant_id,
            details={},
        )

        # 2. Mark tenant as erasing.
        await self._tenants.set_status(tenant_id, TenantStatus.ERASING)

        # 3. Postgres cascade — removes cms_pages, chunks (pgvector), conversations,
        # messages, leads, widgets, allowed_origins, user_tenant_roles, invitations.
        await self._tenants.delete(tenant_id)

        # 4. Redis session purge (T191 seam, Owner B SessionStore protocol).
        await self._session_store.delete_by_tenant(tenant_id)

        # 5. TODO(owner-d, T031/T050): purge MinIO prefix via ObjectStorage.delete_prefix.
        # MinIOObjectStorage raises NotImplementedError until Owner D wires the real client.

        # 6. Audit completion — "minio" omitted until Owner D delivers the adapter.
        await self._audit.log(
            action="tenant_erase_complete",
            outcome=AuditOutcome.SUCCESS,
            actor_user_id=actor_user_id,
            target_tenant_id=tenant_id,
            details={"stores_purged": ["pg", "vector", "redis"]},
        )
