"""Widget repository protocol owned by Slice D."""

from __future__ import annotations

from typing import Protocol
from uuid import UUID

from app.entities.allowed_origin import AllowedOrigin
from app.entities.widget import Widget


class WidgetRepository(Protocol):
    async def get_by_public_id(self, public_id: str) -> Widget | None: ...

    async def is_origin_allowed(self, tenant_id: UUID, origin: str) -> bool: ...

    async def list_allowed_origins(self, tenant_id: UUID) -> list[AllowedOrigin]: ...
