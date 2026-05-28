"""Owner D object storage adapter.

The adapter accepts a MinIO-compatible client so the erasure path can depend on
the ObjectStorage interface without owning MinIO client wiring.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Protocol
from uuid import UUID


class _ObjectInfo(Protocol):
    object_name: str


class _MinioClient(Protocol):
    def remove_object(self, bucket_name: str, object_name: str) -> None: ...

    def list_objects(
        self, bucket_name: str, prefix: str, recursive: bool = False
    ) -> Iterable[_ObjectInfo]: ...


class MinIOObjectStorage:
    def __init__(self, client: _MinioClient | None = None, bucket_name: str = "concierge") -> None:
        self._client = client
        self._bucket_name = bucket_name

    async def store_object(self, tenant_id: UUID, path: str, data: bytes) -> None:
        raise NotImplementedError("MinIO client wiring is pending Owner D deployment work")

    async def fetch_object(self, tenant_id: UUID, path: str) -> bytes:
        raise NotImplementedError("MinIO client wiring is pending Owner D deployment work")

    async def delete_object(self, tenant_id: UUID, path: str) -> None:
        self._require_client().remove_object(self._bucket_name, self._object_name(tenant_id, path))

    async def delete_prefix(self, tenant_id: UUID, prefix: str) -> None:
        client = self._require_client()
        root = self._object_name(tenant_id, prefix).rstrip("/") + "/"
        for obj in client.list_objects(self._bucket_name, prefix=root, recursive=True):
            client.remove_object(self._bucket_name, obj.object_name)

    def _require_client(self) -> _MinioClient:
        if self._client is None:
            raise NotImplementedError("MinIO client wiring is pending Owner D deployment work")
        return self._client

    @staticmethod
    def _object_name(tenant_id: UUID, path: str) -> str:
        return f"tenant-{tenant_id}/{path.lstrip('/')}"
