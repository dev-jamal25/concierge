from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

import pytest

from app.adapters.storage.minio_object_storage import MinIOObjectStorage


@dataclass(frozen=True)
class FakeObject:
    object_name: str


class FakeMinioClient:
    def __init__(self) -> None:
        self.removed: list[tuple[str, str]] = []
        self.prefixes: list[tuple[str, str, bool]] = []

    def list_objects(self, bucket_name: str, prefix: str, recursive: bool = False):
        self.prefixes.append((bucket_name, prefix, recursive))
        return [
            FakeObject(f"{prefix}a.txt"),
            FakeObject(f"{prefix}nested/b.txt"),
        ]

    def remove_object(self, bucket_name: str, object_name: str) -> None:
        self.removed.append((bucket_name, object_name))


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
