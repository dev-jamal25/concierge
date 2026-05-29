"""EraseTenantUseCase (T110, T129) — four-store tenant erasure cascade.

Performs the full Owner A erasure sequence:
  1. Writes a ``tenant_erase_start`` audit entry before any destructive work.
  2. Marks the tenant as ``erasing``.
  3. Cascade-deletes all Postgres rows (which also removes pgvector chunks,
     since they live in Postgres) via TenantRepository.delete.
  4. Purges Redis session keys via the SessionStore protocol (Owner B T029/T191).
  5. Purges MinIO objects under the tenant prefix via the ObjectStorage protocol
     (Owner D T031/T050).
  6. Writes a ``tenant_erase_complete`` audit entry with the full
     ``stores_purged`` list (``["pg", "vector", "redis", "minio"]``) and the
     measured ``duration_ms`` of the purge work.

Concrete adapters (RedisSession, MinIOObjectStorage) are wired in deps.py
(Owner A composition root) and must not be imported here.
"""

from __future__ import annotations

import time
from uuid import UUID

from app.entities.audit_entry import AuditOutcome
from app.entities.tenant import TenantStatus
from app.use_cases.protocols.audit_repository import AuditRepository
from app.use_cases.protocols.object_storage import ObjectStorage
from app.use_cases.protocols.session_store import SessionStore
from app.use_cases.protocols.tenant_repository import TenantRepository


class EraseTenantUseCase:
    def __init__(
        self,
        tenants: TenantRepository,
        audit: AuditRepository,
        session_store: SessionStore,
        object_storage: ObjectStorage,
    ) -> None:
        self._tenants = tenants
        self._audit = audit
        self._session_store = session_store
        self._object_storage = object_storage

    async def execute(self, *, tenant_id: UUID, actor_user_id: UUID) -> None:
        # 1. Write erase-start audit entry BEFORE mutating state (T129 auditor fix).
        await self._audit.log(
            action="tenant_erase_start",
            outcome=AuditOutcome.SUCCESS,
            actor_user_id=actor_user_id,
            target_tenant_id=tenant_id,
            details={},
        )

        # Start measuring purge work after the start-audit so audit-write latency
        # is not counted toward the SLA budget.
        start = time.perf_counter()

        # 2. Mark tenant as erasing.
        await self._tenants.set_status(tenant_id, TenantStatus.ERASING)

        # 3. Postgres cascade — removes cms_pages, chunks (pgvector), conversations,
        # messages, leads, widgets, allowed_origins, user_tenant_roles, invitations.
        await self._tenants.delete(tenant_id)

        # 4. Redis session purge (T191 seam, Owner B SessionStore protocol).
        await self._session_store.delete_by_tenant(tenant_id)

        # 5. MinIO prefix purge (T129 MinIO half, Owner D ObjectStorage protocol).
        # The adapter prepends ``tenant-{tenant_id}/`` to the prefix, so passing an
        # empty string deletes every object owned by this tenant.
        await self._object_storage.delete_prefix(tenant_id, "")

        duration_ms = int((time.perf_counter() - start) * 1000)

        # 6. Audit completion with the full four-store purge manifest.
        await self._audit.log(
            action="tenant_erase_complete",
            outcome=AuditOutcome.SUCCESS,
            actor_user_id=actor_user_id,
            target_tenant_id=tenant_id,
            details={
                "stores_purged": ["pg", "vector", "redis", "minio"],
                "duration_ms": duration_ms,
            },
        )
