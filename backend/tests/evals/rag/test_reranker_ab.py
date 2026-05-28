"""Reranker A/B eval (T183).

Runs the 15-triple RAG golden set twice against a seeded tenant:
  - Pass A: RERANKER_URL set (reranker enabled)
  - Pass B: RERANKER_URL unset (graceful fallback to top-5 by vector score)

Reports hit@5 for both passes and the delta.
Records the result in docs/DECISIONS.md entry #3 (Reranker A/B Result).

Ship-rule: if reranker lifts hit@5 by < 0.05 over no-rerank, prints a
recommendation to disable the reranker (RERANKER_URL unset in v1).
Does NOT fail CI — this is a decision aid, not a regression gate.

Requires: live Postgres + EMBEDDING_API_KEY.
RERANKER_URL is optional; if unset, only the no-reranker pass runs.

Run:
    pytest tests/evals/rag/test_reranker_ab.py -m eval -s
"""

from __future__ import annotations

import json
import os
import pathlib
import uuid
from uuid import UUID

import pytest
import yaml

from tests.evals.rag.test_rag_quality import _PAGE_BODIES

GOLDEN = pathlib.Path(__file__).parent / "golden.jsonl"
THRESHOLDS = pathlib.Path(__file__).parents[4] / "eval_thresholds.yaml"
DECISIONS_MD = pathlib.Path(__file__).parents[5] / "docs" / "DECISIONS.md"

_SHIP_RULE_DELTA = 0.05

pytestmark = [pytest.mark.asyncio, pytest.mark.eval]


@pytest.fixture(scope="module")
async def reranker_tenant():
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
    from sqlalchemy.pool import NullPool

    from app.adapters.embeddings.hosted_embeddings import HostedEmbeddings
    from app.adapters.repositories.chunk_repository import PostgresChunkRepository
    from app.frameworks.config import get_settings
    from app.use_cases.reindex_tenant_chunks import ReindexTenantChunksUseCase

    settings = get_settings()
    if not settings.embedding_api_key:
        pytest.skip("EMBEDDING_API_KEY not set; skipping reranker A/B")

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
            {"id": str(tenant_id), "slug": f"reranker-ab-{tenant_id.hex[:8]}", "dn": "Reranker AB Tenant"},
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
                {"id": str(pid), "tid": str(tenant_id), "title": f"Page {page_key[-4:]}",
                 "body": body, "slug": f"rr-page-{page_key[-4:]}"},
            )

    async with AsyncSession(engine) as db_session:
        chunk_repo = PostgresChunkRepository(db_session)
        embedder = HostedEmbeddings(
            provider=settings.embedding_provider,
            api_key=settings.embedding_api_key,
            model=settings.embedding_model,
        )
        reindex = ReindexTenantChunksUseCase(chunk_repo, embedder)
        for page_key, body in _PAGE_BODIES.items():
            await reindex.execute(cms_page_id=page_ids[page_key], tenant_id=tenant_id, body=body)
        await db_session.commit()

    yield {"tenant_id": tenant_id, "page_ids": page_ids, "engine": engine, "settings": settings}

    async with engine.begin() as conn:
        await conn.execute(text("DELETE FROM tenants WHERE id = :id"), {"id": str(tenant_id)})
    await engine.dispose()


async def _hit_at_5(rows, page_ids, tenant_id, engine, settings, reranker_url, reranker_api_key, reranker_model) -> float:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.adapters.embeddings.hosted_embeddings import HostedEmbeddings
    from app.adapters.repositories.chunk_repository import PostgresChunkRepository
    from app.use_cases.rag_search import RAGSearchUseCase

    hits = 0
    async with AsyncSession(engine) as db_session:
        rag = RAGSearchUseCase(
            PostgresChunkRepository(db_session),
            HostedEmbeddings(
                provider=settings.embedding_provider,
                api_key=settings.embedding_api_key,
                model=settings.embedding_model,
            ),
            reranker_url=reranker_url,
            reranker_api_key=reranker_api_key,
            reranker_model=reranker_model,
        )
        for row in rows:
            expected_pid = page_ids.get(row["expected_cms_page_id"])
            if expected_pid is None:
                continue
            result = await rag.execute(query=row["query"], tenant_id=tenant_id)
            if str(expected_pid) in [str(c.cms_page_id) for c in result.chunks]:
                hits += 1

    return hits / len(rows)


@pytest.mark.asyncio
async def test_reranker_ab(reranker_tenant) -> None:
    tenant_id = reranker_tenant["tenant_id"]
    page_ids = reranker_tenant["page_ids"]
    engine = reranker_tenant["engine"]
    settings = reranker_tenant["settings"]

    rows = [json.loads(l) for l in GOLDEN.read_text().splitlines() if l.strip()]

    # Pass B — no reranker (always runs)
    hit_no_rerank = await _hit_at_5(rows, page_ids, tenant_id, engine, settings,
                                     reranker_url=None, reranker_api_key=None, reranker_model=None)

    reranker_url = settings.reranker_url
    reranker_api_key = settings.reranker_api_key
    reranker_model = settings.reranker_model

    if reranker_url and reranker_api_key:
        hit_rerank = await _hit_at_5(rows, page_ids, tenant_id, engine, settings,
                                      reranker_url=reranker_url, reranker_api_key=reranker_api_key,
                                      reranker_model=reranker_model)
        delta = hit_rerank - hit_no_rerank
    else:
        hit_rerank = None
        delta = None
        print("\n  RERANKER_URL not set — running no-reranker pass only")

    print(f"\n=== Reranker A/B Results ===")
    print(f"  hit@5 (no reranker):  {hit_no_rerank:.3f}")
    if hit_rerank is not None:
        print(f"  hit@5 (with reranker):{hit_rerank:.3f}")
        print(f"  delta:                {delta:+.3f}  (ship-rule threshold: +{_SHIP_RULE_DELTA})")
        if delta < _SHIP_RULE_DELTA:
            print(f"\n  ⚠ RECOMMENDATION: reranker lifts hit@5 by only {delta:.3f} < {_SHIP_RULE_DELTA}.")
            print(f"  Consider setting RERANKER_URL unset in v1 (disable reranker to save cost/latency).")
        else:
            print(f"\n  ✓ Reranker passes ship-rule — recommend enabling in production.")

    # Update DECISIONS.md entry #3 if still unpopulated
    decisions_text = DECISIONS_MD.read_text(encoding="utf-8")
    if "*To be populated by Owner B (T157 / T183)" in decisions_text:
        rerank_str = f"{hit_rerank:.3f}" if hit_rerank is not None else "N/A (RERANKER_URL not set)"
        delta_str = f"{delta:+.3f}" if delta is not None else "N/A"
        ship_str = (
            f"{'PASS — recommend enabling' if delta is not None and delta >= _SHIP_RULE_DELTA else 'FAIL — recommend disabling'}"
            if delta is not None else "N/A"
        )
        entry_content = (
            f"**Date**: 2026-05-28\n"
            f"**Owner**: B (Agent / RAG)\n\n"
            f"| Mode | hit@5 |\n"
            f"|------|-------|\n"
            f"| no reranker | {hit_no_rerank:.3f} |\n"
            f"| with reranker | {rerank_str} |\n"
            f"| delta | {delta_str} |\n\n"
            f"**Ship-rule** (delta ≥ {_SHIP_RULE_DELTA}): {ship_str}\n\n"
            f"Graceful-degradation: `rag_search.py` already falls back to top-5 by vector score "
            f"when `RERANKER_URL` is unset (T169)."
        )
        new_text = decisions_text.replace(
            "*To be populated by Owner B (T157 / T183) after A/B harness run on 15-triple golden set.*\n\n"
            "Topics to cover: `hit@5` with reranker enabled vs. disabled; delta vs. 0.05\n"
            "ship-rule threshold; provider candidates if reranker ships; graceful-degradation\n"
            "behaviour if disabled. FR-019 fallback note if reranker is disabled (query\n"
            "rewriting already live).",
            entry_content,
        )
        DECISIONS_MD.write_text(new_text, encoding="utf-8")
        print(f"\n  → Appended results to {DECISIONS_MD}")
