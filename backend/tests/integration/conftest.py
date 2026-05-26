"""Integration-test fixtures: role-scoped async engines.

Skips the whole integration suite if Postgres is unreachable, so unit tests still
run in environments without the compose stack.
"""

from __future__ import annotations

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from app.frameworks.config import get_settings


def _engine(url: str):
    return create_async_engine(url, poolclass=None, future=True)


@pytest_asyncio.fixture(scope="session")
async def owner_engine():
    settings = get_settings()
    eng = create_async_engine(settings.migration_database_url, future=True)
    try:
        async with eng.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception as exc:  # pragma: no cover - environment dependent
        await eng.dispose()
        pytest.skip(f"Postgres unavailable for integration tests: {exc}")
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture(scope="session")
async def app_engine():
    eng = create_async_engine(get_settings().database_url, future=True)
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture(scope="session")
async def manager_engine():
    settings = get_settings()
    eng = create_async_engine(
        settings.manager_database_url or settings.database_url, future=True
    )
    yield eng
    await eng.dispose()
