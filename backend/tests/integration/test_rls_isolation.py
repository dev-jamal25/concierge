"""RLS isolation tests (T146) — the cross-tenant red-team gate for Owner A tables.

Owner A coverage: tenants, users, user_tenant_roles, invitations, audit_entries.
Asserts:
  - a concierge_app session scoped to Tenant A sees ONLY A's rows;
  - tenant_admin (concierge_app) is denied on audit_entries entirely;
  - concierge_manager can read tenants + audit_entries (elevated), but
  - concierge_manager has NO privilege on content tables (correction #2) — verified
    here against a probe table; full content-table coverage is added by the owning
    slices when those tables exist.

NOTE on prerequisites: requires migration 001 applied. Seeding uses the owner
(superuser) connection, which bypasses RLS; assertions use the role-scoped engines.
"""

from __future__ import annotations

from uuid import uuid4

import pytest
from sqlalchemy import text

pytestmark = pytest.mark.asyncio

TENANT_A = uuid4()
TENANT_B = uuid4()
USER_A = uuid4()
USER_B = uuid4()


async def _seed(owner_engine) -> None:
    async with owner_engine.begin() as conn:
        for tid, slug in ((TENANT_A, "tenant-a"), (TENANT_B, "tenant-b")):
            await conn.execute(
                text(
                    "INSERT INTO tenants (id, slug, display_name) "
                    "VALUES (:id, :slug, :dn) ON CONFLICT (id) DO NOTHING"
                ),
                {"id": str(tid), "slug": slug, "dn": slug.upper()},
            )
        for uid, tid, email in (
            (USER_A, TENANT_A, f"a-{USER_A}@x.test"),
            (USER_B, TENANT_B, f"b-{USER_B}@x.test"),
        ):
            await conn.execute(
                text(
                    "INSERT INTO users (id, email, hashed_password, role) "
                    "VALUES (:id, :email, 'x', 'tenant_admin') ON CONFLICT (id) DO NOTHING"
                ),
                {"id": str(uid), "email": email},
            )
            await conn.execute(
                text(
                    "INSERT INTO user_tenant_roles (user_id, tenant_id) "
                    "VALUES (:uid, :tid) ON CONFLICT DO NOTHING"
                ),
                {"uid": str(uid), "tid": str(tid)},
            )
            await conn.execute(
                text(
                    "INSERT INTO invitations (tenant_id, email, token_hash, expires_at, created_by) "
                    "VALUES (:tid, :email, 'h', now() + interval '1 day', :uid)"
                ),
                {"tid": str(tid), "email": f"inv-{email}", "uid": str(uid)},
            )
            await conn.execute(
                text(
                    "INSERT INTO audit_entries (target_tenant_id, action, outcome) "
                    "VALUES (:tid, 'tenant_create', 'success')"
                ),
                {"tid": str(tid)},
            )


async def _scoped_query(engine, sql: str, tenant_id, user_id=None):
    async with engine.connect() as conn:
        async with conn.begin():
            await conn.execute(
                text("SELECT set_config('app.tenant_id', :tid, true)"),
                {"tid": str(tenant_id)},
            )
            if user_id is not None:
                await conn.execute(
                    text("SELECT set_config('app.user_id', :uid, true)"),
                    {"uid": str(user_id)},
                )
            return (await conn.execute(text(sql))).fetchall()


async def test_tenants_isolated_by_app_role(owner_engine, app_engine) -> None:
    await _seed(owner_engine)
    rows = await _scoped_query(app_engine, "SELECT id FROM tenants", TENANT_A)
    ids = {str(r[0]) for r in rows}
    assert ids == {str(TENANT_A)}
    assert str(TENANT_B) not in ids


async def test_tenant_owned_tables_isolated(owner_engine, app_engine) -> None:
    await _seed(owner_engine)
    for table in ("user_tenant_roles", "invitations"):
        rows = await _scoped_query(
            app_engine, f"SELECT tenant_id FROM {table}", TENANT_A
        )
        tids = {str(r[0]) for r in rows}
        assert tids <= {str(TENANT_A)}, f"{table} leaked another tenant"
        assert str(TENANT_B) not in tids


async def test_app_role_denied_on_audit(owner_engine, app_engine) -> None:
    await _seed(owner_engine)
    with pytest.raises(Exception):  # permission denied / no policy
        await _scoped_query(app_engine, "SELECT id FROM audit_entries", TENANT_A)


async def test_manager_reads_all_tenants_and_audit(owner_engine, manager_engine) -> None:
    await _seed(owner_engine)
    async with manager_engine.connect() as conn:
        tenants = (await conn.execute(text("SELECT id FROM tenants"))).fetchall()
        audit = (await conn.execute(text("SELECT id FROM audit_entries"))).fetchall()
    tenant_ids = {str(r[0]) for r in tenants}
    assert {str(TENANT_A), str(TENANT_B)} <= tenant_ids
    assert len(audit) >= 2


async def test_manager_denied_on_content_tables(owner_engine, manager_engine) -> None:
    """Manager must not be able to read visitor content. Verified against a probe
    table that mimics a content table the manager is never granted on."""
    async with owner_engine.begin() as conn:
        await conn.execute(
            text(
                "CREATE TABLE IF NOT EXISTS _content_probe "
                "(id uuid PRIMARY KEY DEFAULT gen_random_uuid(), tenant_id uuid)"
            )
        )
        # Intentionally NO grant to concierge_manager (mirrors cms/leads/etc.).
        await conn.execute(text("REVOKE ALL ON _content_probe FROM concierge_manager"))
    try:
        with pytest.raises(Exception):  # permission denied for table _content_probe
            async with manager_engine.connect() as conn:
                await conn.execute(text("SELECT * FROM _content_probe"))
    finally:
        async with owner_engine.begin() as conn:
            await conn.execute(text("DROP TABLE IF EXISTS _content_probe"))
