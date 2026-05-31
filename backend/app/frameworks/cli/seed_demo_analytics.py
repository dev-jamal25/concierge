"""Seed realistic analytics data (conversations, messages, leads, escalations)
for the two demo tenants.

Run after seed_demo_tenants.py and seed_demo_users.py. Idempotent: all rows
use fixed UUIDs with ON CONFLICT (id) DO NOTHING.
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

import asyncpg

from app.frameworks.config import get_settings


def _native_asyncpg_url(url: str) -> str:
    return url.replace("postgresql+asyncpg://", "postgresql://", 1)


def _seed_path() -> Path:
    override = os.getenv("DEMO_ANALYTICS_SQL")
    if override:
        return Path(override)
    return Path(__file__).resolve().parents[4] / "db" / "init" / "seed_demo_analytics.sql"


async def seed_demo_analytics() -> str:
    path = _seed_path()
    sql = path.read_text(encoding="utf-8")
    conn = await asyncpg.connect(_native_asyncpg_url(get_settings().migration_database_url))
    try:
        await conn.execute(sql)
    finally:
        await conn.close()
    return f"demo analytics seed applied: {path}"


def main() -> None:
    try:
        message = asyncio.run(seed_demo_analytics())
    except Exception as exc:
        raise SystemExit(f"seed-demo-analytics failed: {exc}") from exc
    print(message)


if __name__ == "__main__":
    main()
