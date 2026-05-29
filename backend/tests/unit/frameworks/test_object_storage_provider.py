from __future__ import annotations

from types import SimpleNamespace

from app.frameworks.api import deps


class FakeMinio:
    def __init__(self, endpoint: str, *, access_key: str, secret_key: str, secure: bool) -> None:
        self.endpoint = endpoint
        self.access_key = access_key
        self.secret_key = secret_key
        self.secure = secure


def test_get_object_storage_wires_minio_client(monkeypatch) -> None:
    settings = SimpleNamespace(
        minio_endpoint="minio:9000",
        minio_access_key="access",
        minio_secret_key="secret",
        minio_bucket="tenant-assets",
        minio_secure=True,
    )
    monkeypatch.setattr(deps, "get_settings", lambda: settings)
    monkeypatch.setattr(deps, "Minio", FakeMinio)

    storage = deps.get_object_storage()

    assert storage._bucket_name == "tenant-assets"
    assert storage._client.endpoint == "minio:9000"
    assert storage._client.access_key == "access"
    assert storage._client.secret_key == "secret"
    assert storage._client.secure is True
