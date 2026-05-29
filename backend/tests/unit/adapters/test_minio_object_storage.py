from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace
from uuid import UUID

import pytest
from minio.error import S3Error

from app.adapters.storage.minio_object_storage import MinIOObjectStorage


@dataclass(frozen=True)
class FakeObject:
    object_name: str


class FakeResponse:
    def __init__(self, payload: bytes) -> None:
        self._payload = payload
        self.closed = False
        self.released = False

    def read(self) -> bytes:
        return self._payload

    def close(self) -> None:
        self.closed = True

    def release_conn(self) -> None:
        self.released = True


class FakeMinioClient:
    def __init__(self) -> None:
        self.objects: dict[tuple[str, str], bytes] = {}
        self.puts: list[tuple[str, str, bytes, int, str]] = []
        self.responses: list[FakeResponse] = []
        self.removed: list[tuple[str, str]] = []
        self.prefixes: list[tuple[str, str, bool]] = []

    def put_object(
        self,
        bucket_name: str,
        object_name: str,
        data,
        length: int,
        content_type: str = "application/octet-stream",
    ) -> None:
        payload = data.read()
        self.objects[(bucket_name, object_name)] = payload
        self.puts.append((bucket_name, object_name, payload, length, content_type))

    def get_object(self, bucket_name: str, object_name: str) -> FakeResponse:
        try:
            payload = self.objects[(bucket_name, object_name)]
        except KeyError as exc:
            raise S3Error(
                SimpleNamespace(),
                "NoSuchKey",
                "object not found",
                object_name,
                "request-id",
                "host-id",
                bucket_name=bucket_name,
                object_name=object_name,
            ) from exc

        response = FakeResponse(payload)
        self.responses.append(response)
        return response

    def list_objects(self, bucket_name: str, prefix: str, recursive: bool = False):
        self.prefixes.append((bucket_name, prefix, recursive))
        return [
            FakeObject(f"{prefix}a.txt"),
            FakeObject(f"{prefix}nested/b.txt"),
        ]

    def remove_object(self, bucket_name: str, object_name: str) -> None:
        self.removed.append((bucket_name, object_name))


@pytest.mark.asyncio
async def test_store_object_writes_bytes_under_tenant_prefix() -> None:
    tenant_id = UUID("00000000-0000-0000-0000-000000000123")
    client = FakeMinioClient()
    storage = MinIOObjectStorage(client=client, bucket_name="concierge-test")

    await storage.store_object(tenant_id, "/uploads/avatar.png", b"image-bytes")

    assert client.puts == [
        (
            "concierge-test",
            "tenant-00000000-0000-0000-0000-000000000123/uploads/avatar.png",
            b"image-bytes",
            len(b"image-bytes"),
            "application/octet-stream",
        )
    ]


@pytest.mark.asyncio
async def test_fetch_object_reads_bytes_and_releases_response() -> None:
    tenant_id = UUID("00000000-0000-0000-0000-000000000123")
    client = FakeMinioClient()
    storage = MinIOObjectStorage(client=client, bucket_name="concierge-test")
    object_name = "tenant-00000000-0000-0000-0000-000000000123/uploads/avatar.png"
    client.objects[("concierge-test", object_name)] = b"image-bytes"

    data = await storage.fetch_object(tenant_id, "uploads/avatar.png")

    assert data == b"image-bytes"
    assert len(client.responses) == 1
    assert client.responses[0].closed is True
    assert client.responses[0].released is True


@pytest.mark.asyncio
async def test_fetch_object_raises_file_not_found_for_missing_object() -> None:
    tenant_id = UUID("00000000-0000-0000-0000-000000000123")
    client = FakeMinioClient()
    storage = MinIOObjectStorage(client=client, bucket_name="concierge-test")

    with pytest.raises(FileNotFoundError) as exc:
        await storage.fetch_object(tenant_id, "uploads/missing.png")

    assert "tenant-00000000-0000-0000-0000-000000000123/uploads/missing.png" in str(
        exc.value
    )


@pytest.mark.asyncio
async def test_store_object_rejects_relative_path_segments() -> None:
    tenant_id = UUID("00000000-0000-0000-0000-000000000123")
    client = FakeMinioClient()
    storage = MinIOObjectStorage(client=client, bucket_name="concierge-test")

    with pytest.raises(ValueError, match="relative segments"):
        await storage.store_object(tenant_id, "../secrets.txt", b"secret")

    assert client.puts == []


@pytest.mark.asyncio
async def test_delete_prefix_removes_all_objects_under_tenant_prefix() -> None:
    tenant_id = UUID("00000000-0000-0000-0000-000000000123")
    client = FakeMinioClient()
    storage = MinIOObjectStorage(client=client, bucket_name="concierge-test")

    await storage.delete_prefix(tenant_id, "uploads")

    assert client.prefixes == [
        ("concierge-test", "tenant-00000000-0000-0000-0000-000000000123/uploads/", True)
    ]
    assert client.removed == [
        (
            "concierge-test",
            "tenant-00000000-0000-0000-0000-000000000123/uploads/a.txt",
        ),
        (
            "concierge-test",
            "tenant-00000000-0000-0000-0000-000000000123/uploads/nested/b.txt",
        ),
    ]
