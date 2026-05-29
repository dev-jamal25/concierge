"""RLS isolation tests for Owner B tables (T082).

Extends the cross-tenant red-team gate to cms_pages, chunks, conversations,
messages, and leads. Asserts: a concierge_app session scoped to Tenant A sees
ONLY A's rows — zero rows from Tenant B leak across the RLS boundary.

Prerequisites: migrations 001 + 002 applied, pgvector extension installed.
Uses the owner (superuser) connection for seeding; role-scoped engines for assertions.

Run: pytest tests/integration/test_rls_isolation_b.py -m integration
"""

from __future__ import annotations

from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import text

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]

TENANT_A = uuid4()
TENANT_B = uuid4()
WIDGET_A = uuid4()
WIDGET_B = uuid4()
PAGE_A = uuid4()
PAGE_B = uuid4()
CONV_A = uuid4()
CONV_B = uuid4()


async def _seed(owner_engine) -> None:  # type: ignore[type-arg]
    async with owner_engine.begin() as conn:
        # Tenants
        for tid, slug in ((TENANT_A, f"rls-b-a-{TENANT_A.hex[:6]}"), (TENANT_B, f"rls-b-b-{TENANT_B.hex[:6]}")):
            await conn.execute(
                text("INSERT INTO tenants (id, slug, display_name) VALUES (:id, :slug, :dn) ON CONFLICT DO NOTHING"),
                {"id": str(tid), "slug": slug, "dn": slug},
            )
        # Widgets (needed by conversations FK)
        for wid, tid in ((WIDGET_A, TENANT_A), (WIDGET_B, TENANT_B)):
            await conn.execute(
                text("INSERT INTO widgets (id, tenant_id, public_id) VALUES (:id, :tid, :pub) ON CONFLICT DO NOTHING"),
                {"id": str(wid), "tid": str(tid), "pub": f"pub-{wid.hex[:8]}"},
            )
        # CMS pages
        for pid, tid in ((PAGE_A, TENANT_A), (PAGE_B, TENANT_B)):
            await conn.execute(
                text(
                    "INSERT INTO cms_pages (id, tenant_id, title, body, state, slug) "
                    "VALUES (:id, :tid, :t, :b, 'published', :slug) ON CONFLICT DO NOTHING"
                ),
                {"id": str(pid), "tid": str(tid), "t": "Page", "b": "body", "slug": f"page-{pid.hex[:6]}"},
            )
        # Chunks (zero vector placeholder)
        zero_vec = "[" + ",".join(["0"] * 1024) + "]"
        for pid, tid in ((PAGE_A, TENANT_A), (PAGE_B, TENANT_B)):
            await conn.execute(
                text(
                    "INSERT INTO chunks (id, tenant_id, cms_page_id, chunk_index, content, embedding) "
                    "VALUES (gen_random_uuid(), :tid, :pid, 0, 'text', CAST(:emb AS vector)) ON CONFLICT DO NOTHING"
                ),
                {"tid": str(tid), "pid": str(pid), "emb": zero_vec},
            )
        # Conversations
        for cid, tid, wid in ((CONV_A, TENANT_A, WIDGET_A), (CONV_B, TENANT_B, WIDGET_B)):
            await conn.execute(
                text(
                    "INSERT INTO conversations (id, tenant_id, widget_id, visitor_session) "
                    "VALUES (:id, :tid, :wid, 'sess') ON CONFLICT DO NOTHING"
                ),
                {"id": str(cid), "tid": str(tid), "wid": str(wid)},
            )
        # Messages
        for cid, tid in ((CONV_A, TENANT_A), (CONV_B, TENANT_B)):
            await conn.execute(
                text(
                    "INSERT INTO messages (id, tenant_id, conversation_id, role, content) "
                    "VALUES (gen_random_uuid(), :tid, :cid, 'visitor', 'hello') ON CONFLICT DO NOTHING"
                ),
                {"tid": str(tid), "cid": str(cid)},
            )
        # Leads
        for cid, tid in ((CONV_A, TENANT_A), (CONV_B, TENANT_B)):
            await conn.execute(
                text(
                    "INSERT INTO leads (id, tenant_id, conversation_id, contact, intent) "
                    "VALUES (gen_random_uuid(), :tid, :cid, 'x@x.com', 'buy') ON CONFLICT DO NOTHING"
                ),
                {"tid": str(tid), "cid": str(cid)},
            )


async def _set_tenant(conn, tenant_id) -> None:  # type: ignore[type-arg]
    await conn.execute(text(f"SET LOCAL app.tenant_id = '{tenant_id}'"))


@pytest_asyncio.fixture(scope="module", autouse=True)
async def seed(owner_engine):  # type: ignore[no-untyped-def]
    await _seed(owner_engine)


async def test_cms_pages_isolation(app_engine) -> None:
    async with app_engine.begin() as conn:
        await _set_tenant(conn, TENANT_A)
        rows = (await conn.execute(text("SELECT tenant_id FROM cms_pages"))).fetchall()
        assert all(str(r[0]) == str(TENANT_A) for r in rows), "cms_pages RLS leak"
        assert len(rows) >= 1


async def test_chunks_isolation(app_engine) -> None:
    async with app_engine.begin() as conn:
        await _set_tenant(conn, TENANT_A)
        rows = (await conn.execute(text("SELECT tenant_id FROM chunks"))).fetchall()
        assert all(str(r[0]) == str(TENANT_A) for r in rows), "chunks RLS leak"


async def test_conversations_isolation(app_engine) -> None:
    async with app_engine.begin() as conn:
        await _set_tenant(conn, TENANT_A)
        rows = (await conn.execute(text("SELECT tenant_id FROM conversations"))).fetchall()
        assert all(str(r[0]) == str(TENANT_A) for r in rows), "conversations RLS leak"


async def test_messages_isolation(app_engine) -> None:
    async with app_engine.begin() as conn:
        await _set_tenant(conn, TENANT_A)
        rows = (await conn.execute(text("SELECT tenant_id FROM messages"))).fetchall()
        assert all(str(r[0]) == str(TENANT_A) for r in rows), "messages RLS leak"


async def test_leads_isolation(app_engine) -> None:
    async with app_engine.begin() as conn:
        await _set_tenant(conn, TENANT_A)
        rows = (await conn.execute(text("SELECT tenant_id FROM leads"))).fetchall()
        assert all(str(r[0]) == str(TENANT_A) for r in rows), "leads RLS leak"


async def test_tenant_b_sees_only_its_own_cms(app_engine) -> None:
    """Reciprocal check: Tenant B cannot see Tenant A's pages."""
    async with app_engine.begin() as conn:
        await _set_tenant(conn, TENANT_B)
        rows = (await conn.execute(text("SELECT id FROM cms_pages WHERE id = :pid"), {"pid": str(PAGE_A)})).fetchall()
        assert rows == [], "Tenant B should NOT see Tenant A's cms_pages"
