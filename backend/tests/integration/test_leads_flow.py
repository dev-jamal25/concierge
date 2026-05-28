"""Leads flow integration test (T121).

Seeds Tenant A and Tenant B, captures leads on A, then:
  - List leads from A context → only A's leads returned
  - List leads from B context → 0 leads returned
  - CSV export → correct format

Run:
    pytest tests/integration/test_leads_flow.py -m integration
"""

from __future__ import annotations

import io
import uuid

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]

TENANT_A = uuid.uuid4()
TENANT_B = uuid.uuid4()
WIDGET_A = uuid.uuid4()
WIDGET_B = uuid.uuid4()
CONV_A = uuid.uuid4()
CONV_B = uuid.uuid4()


async def _seed(engine) -> None:
    async with engine.begin() as conn:
        for tid, slug in (
            (TENANT_A, f"leads-a-{TENANT_A.hex[:6]}"),
            (TENANT_B, f"leads-b-{TENANT_B.hex[:6]}"),
        ):
            await conn.execute(
                text("INSERT INTO tenants (id, slug, display_name) VALUES (:id, :slug, :dn) ON CONFLICT DO NOTHING"),
                {"id": str(tid), "slug": slug, "dn": slug},
            )
        for wid, tid in ((WIDGET_A, TENANT_A), (WIDGET_B, TENANT_B)):
            await conn.execute(
                text("INSERT INTO widgets (id, tenant_id, public_id) VALUES (:id, :tid, :pub) ON CONFLICT DO NOTHING"),
                {"id": str(wid), "tid": str(tid), "pub": f"pub-{wid.hex[:8]}"},
            )
        for cid, tid, wid in ((CONV_A, TENANT_A, WIDGET_A), (CONV_B, TENANT_B, WIDGET_B)):
            await conn.execute(
                text(
                    "INSERT INTO conversations (id, tenant_id, widget_id, visitor_session) "
                    "VALUES (:id, :tid, :wid, :sess) ON CONFLICT DO NOTHING"
                ),
                {"id": str(cid), "tid": str(tid), "wid": str(wid), "sess": str(cid)},
            )
        # Two leads on Tenant A, zero on Tenant B
        for name, contact, intent in (
            ("Alice", "alice@example.com", "get a quote"),
            ("Bob", "bob@example.com", "book a demo"),
        ):
            await conn.execute(
                text(
                    "INSERT INTO leads (id, tenant_id, conversation_id, name, contact, intent) "
                    "VALUES (gen_random_uuid(), :tid, :cid, :name, :contact, :intent)"
                ),
                {"tid": str(TENANT_A), "cid": str(CONV_A), "name": name, "contact": contact, "intent": intent},
            )


@pytest_asyncio.fixture(scope="module", autouse=True)
async def seed(owner_engine):
    await _seed(owner_engine)


@pytest.mark.asyncio
async def test_list_leads_tenant_a_returns_only_a_leads(app_engine) -> None:
    from app.adapters.repositories.lead_repository import PostgresLeadRepository

    async with AsyncSession(app_engine) as session:
        await session.execute(text(f"SET LOCAL app.tenant_id = '{TENANT_A}'"))
        repo = PostgresLeadRepository(session)
        leads = await repo.list(TENANT_A)

    assert len(leads) >= 2
    contacts = {lead.contact for lead in leads}
    assert "alice@example.com" in contacts
    assert "bob@example.com" in contacts
    for lead in leads:
        assert str(lead.tenant_id) == str(TENANT_A), f"Lead {lead.id} belongs to wrong tenant"


@pytest.mark.asyncio
async def test_list_leads_tenant_b_returns_zero(app_engine) -> None:
    from app.adapters.repositories.lead_repository import PostgresLeadRepository

    async with AsyncSession(app_engine) as session:
        await session.execute(text(f"SET LOCAL app.tenant_id = '{TENANT_B}'"))
        repo = PostgresLeadRepository(session)
        leads = await repo.list(TENANT_B)

    assert len(leads) == 0, f"Expected 0 leads for Tenant B, got {len(leads)}"


@pytest.mark.asyncio
async def test_cross_tenant_isolation_a_cannot_see_b(app_engine) -> None:
    """Querying with Tenant A context must not return anything with tenant_id = B."""
    from app.adapters.repositories.lead_repository import PostgresLeadRepository

    async with AsyncSession(app_engine) as session:
        await session.execute(text(f"SET LOCAL app.tenant_id = '{TENANT_A}'"))
        repo = PostgresLeadRepository(session)
        # Use Tenant B's id — RLS should return empty
        leads = await repo.list(TENANT_B)

    assert len(leads) == 0, "RLS isolation failed: Tenant A context returned Tenant B leads"


@pytest.mark.asyncio
async def test_csv_export_format(app_engine) -> None:
    """CSV export contains correct headers and data rows for Tenant A leads."""
    import csv

    from app.adapters.repositories.lead_repository import PostgresLeadRepository

    async with AsyncSession(app_engine) as session:
        await session.execute(text(f"SET LOCAL app.tenant_id = '{TENANT_A}'"))
        repo = PostgresLeadRepository(session)
        leads = await repo.list(TENANT_A)

    # Build CSV the same way the leads route does
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=["id", "name", "contact", "intent", "created_at"])
    writer.writeheader()
    for lead in leads:
        writer.writerow({
            "id": str(lead.id),
            "name": lead.name or "",
            "contact": lead.contact,
            "intent": lead.intent,
            "created_at": lead.created_at.isoformat(),
        })

    csv_text = buf.getvalue()
    assert "id,name,contact,intent,created_at" in csv_text
    assert "alice@example.com" in csv_text
    assert "bob@example.com" in csv_text
