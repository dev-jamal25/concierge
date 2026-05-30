"""Seed demo TENANT_ADMIN users for the two demo tenants.

Run after seed_demo_tenants.py. Idempotent: skips any user whose email
already exists in the database.

Demo credentials:
  Lumière Coffee admin  →  admin@lumiere-coffee.example.com
  Helix Analytics admin →  admin@helix-analytics.example.com
  Password              →  DEMO_ADMIN_PASSWORD env var (default: demo-admin-2025)
"""

from __future__ import annotations

import asyncio
import os
from uuid import UUID

from sqlalchemy.ext.asyncio import async_sessionmaker

from app.adapters.repositories.user_repository import PostgresUserRepository
from app.entities.user import UserRole
from app.frameworks.api.session_auth import hash_password
from app.frameworks.config import get_settings
from app.frameworks.db.base import make_engine

_LUMIERE_TENANT_ID = UUID("a1000000-0000-0000-0000-000000000000")
_HELIX_TENANT_ID = UUID("b2000000-0000-0000-0000-000000000000")

_DEMO_USERS = [
    ("admin@lumiere-coffee.example.com", _LUMIERE_TENANT_ID, "Lumière Coffee"),
    ("admin@helix-analytics.example.com", _HELIX_TENANT_ID, "Helix Analytics"),
]


async def seed_demo_users(password: str) -> list[str]:
    settings = get_settings()
    engine = make_engine(settings.migration_database_url)
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    messages: list[str] = []
    try:
        async with sessionmaker() as session:
            async with session.begin():
                users = PostgresUserRepository(session)
                for email, tenant_id, label in _DEMO_USERS:
                    existing = await users.get_by_email(email)
                    if existing is not None:
                        messages.append(f"  already exists: {email} ({label})")
                        continue
                    created = await users.create(
                        email=email,
                        hashed_password=hash_password(password),
                        role=UserRole.TENANT_ADMIN,
                    )
                    await users.bind_tenant_role(created.id, tenant_id)
                    messages.append(f"  created tenant_admin: {email} ({label})")
    finally:
        await engine.dispose()
    return messages


def main() -> None:
    password = os.getenv("DEMO_ADMIN_PASSWORD", "demo-admin-2025")
    try:
        messages = asyncio.run(seed_demo_users(password))
    except Exception as exc:
        raise SystemExit(f"seed-demo-users failed: {exc}") from exc
    for msg in messages:
        print(msg)
    print("done — log in at http://localhost:8501 with the email above")
    print(f"password: {password}")


if __name__ == "__main__":
    main()
