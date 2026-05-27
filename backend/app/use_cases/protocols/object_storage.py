"""Object storage protocol owned by Slice D."""

from __future__ import annotations

from typing import Protocol
from uuid import UUID


class ObjectStorage(Protocol):
    async def store_object(self, tenant_id: UUID, path: str, data: bytes) -> None: ...

    async def fetch_object(self, tenant_id: UUID, path: str) -> bytes: ...

    async def delete_object(self, tenant_id: UUID, path: str) -> None: ...

    async def delete_prefix(self, tenant_id: UUID, prefix: str) -> None: ...
