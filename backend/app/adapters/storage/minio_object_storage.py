"""Owner D object storage adapter placeholder.

The runtime image does not currently include a MinIO Python client. This adapter
keeps the concrete seam in place without adding dependencies or changing the
shared lockfile; methods fail loudly until the storage client is wired by the
deployment/CI pass.
"""

from __future__ import annotations

from uuid import UUID


class MinIOObjectStorage:
    async def store_object(self, tenant_id: UUID, path: str, data: bytes) -> None:
        raise NotImplementedError("MinIO client wiring is pending Owner D deployment work")

    async def fetch_object(self, tenant_id: UUID, path: str) -> bytes:
        raise NotImplementedError("MinIO client wiring is pending Owner D deployment work")

    async def delete_object(self, tenant_id: UUID, path: str) -> None:
        raise NotImplementedError("MinIO client wiring is pending Owner D deployment work")

    async def delete_prefix(self, tenant_id: UUID, prefix: str) -> None:
        raise NotImplementedError("MinIO client wiring is pending Owner D deployment work")
