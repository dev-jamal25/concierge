"""Apply the idempotent demo tenant seed after migrations."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

import asyncpg

from app.frameworks.config import get_settings


def _native_asyncpg_url(url: str) -> str:
    return url.replace("postgresql+asyncpg://", "postgresql://", 1)


def _seed_path() -> Path:
    override = os.getenv("DEMO_SEED_SQL")
    if override:
        return Path(override)
    return Path(__file__).resolve().parents[4] / "db" / "init" / "seed_demo_tenants.sql"


async def seed_demo_tenants() -> str:
    path = _seed_path()
    sql = path.read_text(encoding="utf-8")
    conn = await asyncpg.connect(_native_asyncpg_url(get_settings().migration_database_url))
    try:
        await conn.execute(sql)
    finally:
        await conn.close()
    return f"demo tenant seed applied: {path}"


def main() -> None:
    try:
        message = asyncio.run(seed_demo_tenants())
    except Exception as exc:
        raise SystemExit(f"seed-demo-tenant failed: {exc}") from exc
    print(message)


if __name__ == "__main__":
    main()
