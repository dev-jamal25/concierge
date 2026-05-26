"""SQLAlchemy declarative base + async engine/sessionmaker (T013 — [ALL] stub).

This is Layer 4 (frameworks). Nothing in entities/ or use_cases/ may import it.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.frameworks.config import get_settings


class Base(DeclarativeBase):
    """Declarative base for all ORM models (defined in models.py)."""


def make_engine(database_url: str | None = None) -> AsyncEngine:
    url = database_url or get_settings().database_url
    return create_async_engine(url, pool_pre_ping=True, future=True)


# Default app-role engine (concierge_app — bound by RLS).
engine: AsyncEngine = make_engine()

SessionLocal = async_sessionmaker(engine, expire_on_commit=False)
