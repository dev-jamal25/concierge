"""Bootstrap one tenant_manager user from environment variables."""

from __future__ import annotations

import asyncio
import os

from sqlalchemy.ext.asyncio import async_sessionmaker

from app.adapters.repositories.user_repository import PostgresUserRepository
from app.entities.user import UserRole
from app.frameworks.api.session_auth import hash_password
from app.frameworks.config import get_settings
from app.frameworks.db.base import make_engine


def _required_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"{name} must be set")
    return value


async def bootstrap_manager() -> str:
    email = _required_env("BOOTSTRAP_MANAGER_EMAIL").strip().lower()
    password = _required_env("BOOTSTRAP_MANAGER_PASSWORD")
    settings = get_settings()
    engine = make_engine(settings.migration_database_url)
    sessionmaker = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with sessionmaker() as session:
            async with session.begin():
                users = PostgresUserRepository(session)
                existing = await users.get_by_email(email)
                if existing is not None:
                    return f"tenant_manager already exists: {email}"
                await users.create(
                    email=email,
                    hashed_password=hash_password(password),
                    role=UserRole.TENANT_MANAGER,
                )
                return f"tenant_manager created: {email}"
    finally:
        await engine.dispose()


def main() -> None:
    try:
        message = asyncio.run(bootstrap_manager())
    except Exception as exc:
        raise SystemExit(f"bootstrap-manager failed: {exc}") from exc
    print(message)


if __name__ == "__main__":
    main()
