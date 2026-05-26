"""Async session factory + per-request tenant scoping (T017).

`tenant_id` is propagated via a ContextVar set by TenantContextMiddleware from
the *verified* token/session only (never request body — correction #4). The
session dependency applies it as a transaction-local GUC using
`set_config('app.tenant_id', <uuid>, true)`, so Postgres RLS policies filter on
`current_setting('app.tenant_id')::uuid`. Transaction-local means the value
never leaks across requests on a pooled connection.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextvars import ContextVar

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.frameworks.config import get_settings
from app.frameworks.db.base import SessionLocal, make_engine

# Set by TenantContextMiddleware; None for unauthenticated / manager-global requests.
tenant_id_ctx: ContextVar[str | None] = ContextVar("tenant_id_ctx", default=None)
# Set by the auth layer for the authenticated principal (drives the users RLS policy).
user_id_ctx: ContextVar[str | None] = ContextVar("user_id_ctx", default=None)


def set_tenant_id(tenant_id: str | None):
    return tenant_id_ctx.set(tenant_id)


def reset_tenant_id(token) -> None:
    tenant_id_ctx.reset(token)


def set_user_id(user_id: str | None):
    return user_id_ctx.set(user_id)


def reset_user_id(token) -> None:
    user_id_ctx.reset(token)


async def _apply_tenant_guc(session: AsyncSession) -> None:
    # Parameterized + transaction-local (third arg true). SET LOCAL cannot bind
    # params, so set_config() is used instead.
    tid = tenant_id_ctx.get()
    if tid is not None:
        await session.execute(
            text("SELECT set_config('app.tenant_id', :tid, true)"), {"tid": str(tid)}
        )
    uid = user_id_ctx.get()
    if uid is not None:
        await session.execute(
            text("SELECT set_config('app.user_id', :uid, true)"), {"uid": str(uid)}
        )


async def get_session() -> AsyncIterator[AsyncSession]:
    """Request-scoped session bound to the concierge_app role (RLS-enforced)."""
    async with SessionLocal() as session:
        async with session.begin():
            await _apply_tenant_guc(session)
            yield session


# --- Manager-role session (concierge_manager): elevated reads on tenants +
# audit_entries + usage aggregate ONLY. Never used for content tables. ---

_manager_sessionmaker: async_sessionmaker[AsyncSession] | None = None


def _get_manager_sessionmaker() -> async_sessionmaker[AsyncSession]:
    global _manager_sessionmaker
    if _manager_sessionmaker is None:
        settings = get_settings()
        url = settings.manager_database_url or settings.database_url
        _manager_sessionmaker = async_sessionmaker(make_engine(url), expire_on_commit=False)
    return _manager_sessionmaker


async def get_manager_session() -> AsyncIterator[AsyncSession]:
    """Session bound to the concierge_manager role. Its grants (set in the
    migrations) restrict it to tenants + audit_entries + usage aggregates."""
    async with _get_manager_sessionmaker()() as session:
        async with session.begin():
            yield session
