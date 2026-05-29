"""Widget origin integration tests (T105)."""

from __future__ import annotations

import os
from collections.abc import AsyncIterator, Iterator
from datetime import timedelta
from uuid import uuid4

import pytest
import pytest_asyncio
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.frameworks.api.deps import get_token_signer, manager_db_session
from app.frameworks.api.main import create_app

os.environ.setdefault("SERVICE_TOKEN", "test-token-widget-origin")

ALLOWED_ORIGIN = "https://allowed.example.com"
BLOCKED_ORIGIN = "https://blocked.example.com"


class FakeWidgetSigner:
    def __init__(self) -> None:
        self.claims: dict = {}

    def sign_token(self, claims, ttl: timedelta) -> str:
        self.claims = dict(claims)
        return "fake-widget-token"

    def verify_token(self, token: str) -> dict:
        if token != "fake-widget-token":
            raise ValueError("invalid token")
        return self.claims


@pytest_asyncio.fixture(autouse=True)
async def _require_schema(owner_engine):
    async with owner_engine.connect() as conn:
        exists = (await conn.execute(text("SELECT to_regclass('public.widgets')"))).scalar()
    if exists is None:
        pytest.skip("schema not migrated; run `alembic upgrade head` first")


@pytest.fixture
def client(manager_engine) -> Iterator[tuple[TestClient, FakeWidgetSigner]]:
    app = create_app()
    signer = FakeWidgetSigner()
    sessionmaker = async_sessionmaker(manager_engine, expire_on_commit=False)

    async def override_manager_db_session() -> AsyncIterator[AsyncSession]:
        async with sessionmaker() as session:
            async with session.begin():
                yield session

    app.dependency_overrides[manager_db_session] = override_manager_db_session
    app.dependency_overrides[get_token_signer] = lambda: signer
    with TestClient(app) as test_client:
        yield test_client, signer
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_widget_token_origin_gate_and_chat_origin_mismatch(
    client: tuple[TestClient, FakeWidgetSigner],
    owner_engine,
) -> None:
    test_client, _signer = client
    tenant_id = uuid4()
    widget_id = uuid4()
    public_id = f"wgt_{widget_id.hex[:12]}"

    async with owner_engine.begin() as conn:
        await conn.execute(
            text("INSERT INTO tenants (id, slug, display_name) VALUES (:id, :slug, :name)"),
            {
                "id": str(tenant_id),
                "slug": f"widget-origin-{tenant_id.hex[:8]}",
                "name": "Widget Origin Test",
            },
        )
        await conn.execute(
            text(
                "INSERT INTO widgets (id, tenant_id, public_id, is_enabled) "
                "VALUES (:id, :tenant_id, :public_id, true)"
            ),
            {
                "id": str(widget_id),
                "tenant_id": str(tenant_id),
                "public_id": public_id,
            },
        )
        await conn.execute(
            text(
                "INSERT INTO allowed_origins (tenant_id, origin) "
                "VALUES (:tenant_id, :origin)"
            ),
            {"tenant_id": str(tenant_id), "origin": ALLOWED_ORIGIN},
        )

    allowed = test_client.post(
        "/widget/token",
        json={"widget_id": public_id, "origin": ALLOWED_ORIGIN},
    )
    assert allowed.status_code == 200, allowed.text
    token = allowed.json()["token"]

    blocked = test_client.post(
        "/widget/token",
        json={"widget_id": public_id, "origin": BLOCKED_ORIGIN},
    )
    assert blocked.status_code == 403, blocked.text

    config_mismatch = test_client.get(
        "/widget/config",
        headers={"Authorization": f"Bearer {token}", "Origin": BLOCKED_ORIGIN},
    )
    assert config_mismatch.status_code == 403, config_mismatch.text

    chat_mismatch = test_client.post(
        "/chat",
        headers={"Authorization": f"Bearer {token}", "Origin": BLOCKED_ORIGIN},
        json={"conversation_id": str(uuid4()), "message": "hello"},
    )
    assert chat_mismatch.status_code == 403, chat_mismatch.text
