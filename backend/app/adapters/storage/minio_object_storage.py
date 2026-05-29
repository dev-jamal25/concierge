"""Owner D object storage adapter.

The adapter accepts a MinIO-compatible client so the erasure path can depend on
the ObjectStorage interface without owning MinIO client wiring.
"""

from __future__ import annotations

from collections.abc import Iterable
from io import BytesIO
from typing import Protocol
from uuid import UUID

from minio.error import S3Error


class _ObjectInfo(Protocol):
    object_name: str


class _ObjectResponse(Protocol):
    def read(self) -> bytes: ...

    def close(self) -> None: ...

    def release_conn(self) -> None: ...


class _MinioClient(Protocol):
    def put_object(
        self,
        bucket_name: str,
        object_name: str,
        data: BytesIO,
        length: int,
        content_type: str = "application/octet-stream",
    ) -> object: ...

    def get_object(self, bucket_name: str, object_name: str) -> _ObjectResponse: ...

    def remove_object(self, bucket_name: str, object_name: str) -> None: ...

    def list_objects(
        self, bucket_name: str, prefix: str, recursive: bool = False
    ) -> Iterable[_ObjectInfo]: ...


class MinIOObjectStorage:
    def __init__(self, client: _MinioClient | None = None, bucket_name: str = "concierge") -> None:
        self._client = client
        self._bucket_name = bucket_name

    async def store_object(self, tenant_id: UUID, path: str, data: bytes) -> None:
        self._require_client().put_object(
            self._bucket_name,
            self._object_name(tenant_id, path),
            BytesIO(data),
            len(data),
            content_type="application/octet-stream",
        )

    async def fetch_object(self, tenant_id: UUID, path: str) -> bytes:
        object_name = self._object_name(tenant_id, path)
        try:
            response = self._require_client().get_object(self._bucket_name, object_name)
        except S3Error as exc:
            if exc.code in {"NoSuchKey", "NoSuchObject"}:
                raise FileNotFoundError(object_name) from exc
            raise

        try:
            return response.read()
        finally:
            response.close()
            response.release_conn()

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
        clean_path = MinIOObjectStorage._clean_path(path)
        return f"tenant-{tenant_id}/{clean_path}" if clean_path else f"tenant-{tenant_id}/"

    @staticmethod
    def _clean_path(path: str) -> str:
        parts = [part for part in path.replace("\\", "/").split("/") if part]
        if any(part in {".", ".."} for part in parts):
            raise ValueError("object path must not contain relative segments")
        return "/".join(parts)
