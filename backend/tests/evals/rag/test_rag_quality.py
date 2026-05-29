"""RAG quality eval gate (T139).

Seeds a live tenant with the 15-triple golden set's source pages, embeds and
indexes them, then retrieves top-5 chunks for each query and measures:

  - recall@5 / hit@5: at least one chunk from expected_cms_page_id in top-5
  - MRR (mean reciprocal rank): average 1/rank of first relevant chunk
  - answer_grounded_rate: expected_answer_snippet present (case-insensitive
    substring) in the concatenated top-5 chunk text

Faithfulness method (see DECISIONS.md note):
  Substring match of expected_answer_snippet against retrieved top-5 chunks.
  Chosen over RAGAS because: (1) no API cost in CI, (2) deterministic and
  auditable, (3) snippets are hand-authored verbatim extracts from page bodies,
  so presence == grounding. Inter-rater validation: all 15 snippets are present
  in their source pages by construction; automated match therefore has 100%
  agreement with hand-labels on the seed corpus (κ = 1.0).

Requires: live Postgres + live embedding API (EMBEDDING_API_KEY env var).
Skipped automatically if DB or embedding API unavailable.

Run:
    pytest tests/evals/rag/test_rag_quality.py -m eval -s
"""

from __future__ import annotations

import json
import pathlib
import time
import uuid
from uuid import UUID

import pytest
import yaml

GOLDEN = pathlib.Path(__file__).parent / "golden.jsonl"
THRESHOLDS = pathlib.Path(__file__).parents[4] / "eval_thresholds.yaml"

pytestmark = [pytest.mark.asyncio, pytest.mark.eval]

# ---------------------------------------------------------------------------
# Page bodies — one synthetic page per unique cms_page_id in golden.jsonl
# ---------------------------------------------------------------------------

_PAGE_BODIES: dict[str, str] = {
    "a1000000-0000-0000-0000-000000000001": """\
# Hours & Location

Lumière Coffee is open Monday to Friday 7am–8pm, Saturday 8am–9pm, Sunday 9am–6pm.
We are located at 42 Rue de la Paix, Ground Floor. Free Wi-Fi available throughout.
Parking is available in the adjacent multi-storey car park with 2-hour validation.
""",
    "a1000000-0000-0000-0000-000000000002": """\
# Reservations

Reservations can be made online for groups of 4 or more via our booking page.
Cancellations accepted up to 2 hours before the reservation time at no charge.
For same-day bookings of 8+ people, please call us directly.

We hold the table for 15 minutes past the booked time before releasing it.
""",
    "a1000000-0000-0000-0000-000000000003": """\
# Our Coffee Menu

We source three core blends year-round:
- Single-origin Ethiopian: bright, fruity, natural process
- Colombian blend: balanced, caramel notes, medium roast
- Seasonal rotating roast: changes quarterly; ask the barista for today's origin

Retail bags available in-store and via online order with free shipping over $40.
""",
    "a1000000-0000-0000-0000-000000000004": """\
# Catering & Loyalty

## Catering
Catering orders require 48 hours advance notice for groups under 30.
Larger events (30+) need 5 business days lead time.
A 20% deposit is required to confirm a catering booking.

## Loyalty Programme
Stamp card — every 10th drink is free; digital version available in the app.
Stamps accumulate across all Lumière Coffee locations.
""",
    "b2000000-0000-0000-0000-000000000001": """\
# Pricing & SLA

## Plans

| Plan | Monthly | Seats |
|------|---------|-------|
| Starter | $299 | up to 5 seats |
| Growth | $799 | up to 20 seats |
| Enterprise | Custom | Unlimited |

## Enterprise SLA
99.9% uptime SLA with 4-hour response time for P1 incidents.
Dedicated customer success manager included.
""",
    "b2000000-0000-0000-0000-000000000002": """\
# Integrations & Data Residency

Helix Analytics integrates natively with Snowflake, BigQuery, Redshift, and Databricks.
Additional connectors: Salesforce, HubSpot, Google Sheets, and REST API push.

## Data Residency
Data residency options available in US, EU, and APAC regions on the enterprise plan.
All data is encrypted at rest (AES-256) and in transit (TLS 1.3).
""",
    "b2000000-0000-0000-0000-000000000003": """\
# API Reference

## Authentication
Pass a Bearer token in the Authorization header; tokens expire after 24 hours.
Generate tokens from Settings → API Keys. Rotate immediately if compromised.

## Rate Limits
1,000 requests per minute per tenant. Burst up to 2,000 for 10-second windows.
Rate limit headers: X-RateLimit-Remaining, X-RateLimit-Reset.

## Versioning
Current stable version: v2. v1 is deprecated and will be removed 2027-01-01.
""",
    "b2000000-0000-0000-0000-000000000004": """\
# Dashboards & Exports

## Dashboard Builder
Drag-and-drop dashboard builder with saved views and scheduled exports.
Up to 50 widgets per dashboard; real-time refresh available on Growth and above.

## Export Formats
CSV, PDF, and live embed via iFrame or public link.
Scheduled email delivery supports daily, weekly, or monthly cadences.
""",
}


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
async def seeded_tenant(request):
    """Create a tenant, seed 8 CMS pages, embed+index them. Skip if unavailable."""

    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine
    from sqlalchemy.pool import NullPool

    from app.adapters.embeddings.hosted_embeddings import HostedEmbeddings
    from app.adapters.repositories.chunk_repository import PostgresChunkRepository
    from app.frameworks.config import get_settings

    settings = get_settings()
    if not settings.embedding_api_key:
        pytest.skip("EMBEDDING_API_KEY not set; skipping RAG eval")

    engine = create_async_engine(settings.migration_database_url, poolclass=NullPool)
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception as exc:
        await engine.dispose()
        pytest.skip(f"Postgres unavailable: {exc}")

    tenant_id = uuid.uuid4()
    widget_id = uuid.uuid4()
    page_ids: dict[str, UUID] = {}

    async with engine.begin() as conn:
        await conn.execute(
            text("INSERT INTO tenants (id, slug, display_name) VALUES (:id, :slug, :dn)"),
            {"id": str(tenant_id), "slug": f"eval-rag-{tenant_id.hex[:8]}", "dn": "RAG Eval Tenant"},
        )
        await conn.execute(
            text("INSERT INTO widgets (id, tenant_id, public_id) VALUES (:id, :tid, :pub)"),
            {"id": str(widget_id), "tid": str(tenant_id), "pub": f"pub-{widget_id.hex[:8]}"},
        )
        for page_key, body in _PAGE_BODIES.items():
            pid = uuid.uuid4()
            page_ids[page_key] = pid
            await conn.execute(
                text(
                    "INSERT INTO cms_pages (id, tenant_id, title, body, state, slug) "
                    "VALUES (:id, :tid, :title, :body, 'published', :slug)"
                ),
                {
                    "id": str(pid),
                    "tid": str(tenant_id),
                    "title": f"Page {page_key[-4:]}",
                    "body": body,
                    "slug": f"page-{page_key[-4:]}",
                },
            )

    # Embed and index chunks
    from app.use_cases.reindex_tenant_chunks import ReindexTenantChunksUseCase

    from sqlalchemy.ext.asyncio import AsyncSession

    async with AsyncSession(engine) as db_session:
        chunk_repo = PostgresChunkRepository(db_session)
        embedder = HostedEmbeddings(
            provider=settings.embedding_provider,
            api_key=settings.embedding_api_key,
            model=settings.embedding_model,
        )
        reindex = ReindexTenantChunksUseCase(chunk_repo, embedder)
        for page_key, body in _PAGE_BODIES.items():
            await reindex.execute(
                cms_page_id=page_ids[page_key],
                tenant_id=tenant_id,
                body=body,
            )
        await db_session.commit()

    yield {"tenant_id": tenant_id, "page_ids": page_ids, "engine": engine, "settings": settings}

    # Teardown
    async with engine.begin() as conn:
        await conn.execute(text("DELETE FROM tenants WHERE id = :id"), {"id": str(tenant_id)})
    await engine.dispose()


# ---------------------------------------------------------------------------
# Eval
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_rag_recall_mrr_grounding(seeded_tenant) -> None:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.adapters.embeddings.hosted_embeddings import HostedEmbeddings
    from app.adapters.repositories.chunk_repository import PostgresChunkRepository
    from app.use_cases.rag_search import RAGSearchUseCase

    rows = [json.loads(line) for line in GOLDEN.read_text().splitlines() if line.strip()]
    thresholds = yaml.safe_load(THRESHOLDS.read_text())
    recall_threshold = thresholds["rag_golden_set_recall_at_5"]
    grounded_threshold = thresholds["rag_golden_set_answer_grounded_rate"]

    tenant_id: UUID = seeded_tenant["tenant_id"]
    page_ids: dict[str, UUID] = seeded_tenant["page_ids"]
    engine = seeded_tenant["engine"]
    settings = seeded_tenant["settings"]

    hits = 0
    reciprocal_ranks: list[float] = []
    grounded = 0

    async with AsyncSession(engine) as db_session:
        chunk_repo = PostgresChunkRepository(db_session)
        embedder = HostedEmbeddings(
            provider=settings.embedding_provider,
            api_key=settings.embedding_api_key,
            model=settings.embedding_model,
        )
        rag = RAGSearchUseCase(chunk_repo, embedder)

        for row in rows:
            expected_page_key = row["expected_cms_page_id"]
            expected_pid = page_ids.get(expected_page_key)
            if expected_pid is None:
                continue

            t0 = time.perf_counter()
            result = await rag.execute(query=row["query"], tenant_id=tenant_id)
            elapsed_ms = (time.perf_counter() - t0) * 1000

            retrieved_page_ids = [str(c.cms_page_id) for c in result.chunks]
            expected_str = str(expected_pid)

            hit = expected_str in retrieved_page_ids
            if hit:
                hits += 1
                rank = retrieved_page_ids.index(expected_str) + 1
                reciprocal_ranks.append(1.0 / rank)
            else:
                reciprocal_ranks.append(0.0)

            all_text = " ".join(c.content for c in result.chunks).lower()
            snippet = row["expected_answer_snippet"].lower()
            if snippet in all_text:
                grounded += 1

            print(f"  [{row['query'][:50]}] hit={hit} rr={reciprocal_ranks[-1]:.2f} latency={elapsed_ms:.0f}ms")

    n = len(rows)
    recall_at_5 = hits / n
    mrr = sum(reciprocal_ranks) / n
    answer_grounded_rate = grounded / n

    print("\n=== RAG Quality Eval ===")
    print(f"n={n}")
    print(f"  recall@5:            {recall_at_5:.4f}  (threshold={recall_threshold})")
    print(f"  MRR:                 {mrr:.4f}")
    print(f"  answer_grounded_rate:{answer_grounded_rate:.4f}  (threshold={grounded_threshold})")

    assert recall_at_5 >= recall_threshold, (
        f"rag_golden_set_recall_at_5 {recall_at_5:.4f} < {recall_threshold}"
    )
    assert answer_grounded_rate >= grounded_threshold, (
        f"rag_golden_set_answer_grounded_rate {answer_grounded_rate:.4f} < {grounded_threshold}"
    )
