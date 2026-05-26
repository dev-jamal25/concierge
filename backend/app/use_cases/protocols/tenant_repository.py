"""TenantRepository protocol (T019) — Layer 2 interface.

Owner A publishes this seam; B/C/D code against it (never the concrete adapter).
Covers tenants plus the provisioning-time rows on widgets / allowed_origins.
"""

from __future__ import annotations

from typing import Protocol
from uuid import UUID

from app.entities.allowed_origin import AllowedOrigin
from app.entities.tenant import Tenant, TenantStatus


class TenantRepository(Protocol):
    async def create(
        self,
        *,
        slug: str,
        display_name: str,
        plan: str = "poc",
        persona_config: dict | None = None,
        theme_config: dict | None = None,
        guardrail_config: dict | None = None,
    ) -> Tenant: ...

    async def get(self, tenant_id: UUID) -> Tenant | None: ...

    async def get_by_slug(self, slug: str) -> Tenant | None: ...

    async def list(self) -> list[Tenant]: ...

    async def update(self, tenant_id: UUID, **changes: object) -> Tenant: ...

    async def set_status(self, tenant_id: UUID, status: TenantStatus) -> None: ...

    async def delete(self, tenant_id: UUID) -> None:
        """Cascade-delete the tenant and all tenant-scoped rows (erasure, PG store)."""
        ...

    async def add_allowed_origin(self, tenant_id: UUID, origin: str) -> AllowedOrigin: ...

    async def list_allowed_origins(self, tenant_id: UUID) -> list[AllowedOrigin]: ...

    async def create_widget(self, tenant_id: UUID, public_id: str) -> None: ...
