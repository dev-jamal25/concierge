"""Integration-test fixtures: role-scoped async engines.

Skips the whole integration suite if Postgres is unreachable, so unit tests still
run in environments without the compose stack.
"""

from __future__ import annotations

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool

from app.frameworks.config import get_settings


def _engine(url: str):
    return create_async_engine(url, poolclass=NullPool, future=True)


@pytest_asyncio.fixture
async def owner_engine():
    settings = get_settings()
    eng = _engine(settings.migration_database_url)
    try:
        async with eng.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception as exc:  # pragma: no cover - environment dependent
        await eng.dispose()
        pytest.skip(f"Postgres unavailable for integration tests: {exc}")
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def app_engine():
    eng = _engine(get_settings().database_url)
    yield eng
    await eng.dispose()


@pytest_asyncio.fixture
async def manager_engine():
    settings = get_settings()
    eng = _engine(settings.manager_database_url or settings.database_url)
    yield eng
    await eng.dispose()
