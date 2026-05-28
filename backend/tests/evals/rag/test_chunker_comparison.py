"""Chunker bake-off eval (T182).

For each of the three chunker variants [fixed_500, paragraph_aware, header_first]:
  1. Re-chunks and re-embeds the 8 seed pages from the RAG golden set.
  2. Runs all 15 golden queries and measures hit@5, MRR, mean retrieval latency.
  3. Emits a Markdown comparison table to stdout.
  4. Appends the table + winner to docs/DECISIONS.md as Entry #1.5.

Winner = highest hit@5 satisfying rag_golden_set_recall_at_5 ≥ 0.85 AND
latency ≤ 200ms p95. Ties broken by MRR then lower latency.

Does NOT fail CI on its own (decision aid). The RAG gate in test_rag_quality.py
is the regression gate.

Requires: live Postgres + EMBEDDING_API_KEY.

Run:
    pytest tests/evals/rag/test_chunker_comparison.py -m eval -s
"""

from __future__ import annotations

import json
import pathlib
import statistics
import time
import uuid
from uuid import UUID

import pytest
import yaml

from tests.evals.rag.test_rag_quality import _PAGE_BODIES

GOLDEN = pathlib.Path(__file__).parent / "golden.jsonl"
THRESHOLDS = pathlib.Path(__file__).parents[4] / "eval_thresholds.yaml"
DECISIONS_MD = pathlib.Path(__file__).parents[5] / "docs" / "DECISIONS.md"

pytestmark = [pytest.mark.asyncio, pytest.mark.eval]

_CHUNKERS = ["fixed_500", "paragraph_aware", "header_first"]


@pytest.fixture(scope="module")
async def eval_engine():
    import os

    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine
    from sqlalchemy.pool import NullPool

    from app.frameworks.config import get_settings

    settings = get_settings()
    if not settings.embedding_api_key:
        pytest.skip("EMBEDDING_API_KEY not set; skipping chunker bake-off")

    engine = create_async_engine(settings.migration_database_url, poolclass=NullPool)
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception as exc:
        await engine.dispose()
        pytest.skip(f"Postgres unavailable: {exc}")

    yield engine, settings
    await engine.dispose()


async def _run_variant(chunker_name: str, rows: list[dict], engine, settings) -> dict:
    import os
    os.environ["CHUNKER"] = chunker_name

    # Invalidate cached _load_chunker by reimporting
    import importlib
    import app.use_cases.reindex_tenant_chunks as rtc
    importlib.reload(rtc)

    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.adapters.embeddings.hosted_embeddings import HostedEmbeddings
    from app.adapters.repositories.chunk_repository import PostgresChunkRepository
    from app.use_cases.rag_search import RAGSearchUseCase

    tenant_id = uuid.uuid4()
    widget_id = uuid.uuid4()
    page_ids: dict[str, UUID] = {}

    async with engine.begin() as conn:
        await conn.execute(
            text("INSERT INTO tenants (id, slug, display_name) VALUES (:id, :slug, :dn)"),
            {"id": str(tenant_id), "slug": f"bakeoff-{chunker_name}-{tenant_id.hex[:6]}", "dn": f"Bakeoff {chunker_name}"},
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
                {"id": str(pid), "tid": str(tenant_id), "title": f"Page {page_key[-4:]}", "body": body, "slug": f"page-{page_key[-4:]}-{chunker_name}"},
            )

    async with AsyncSession(engine) as db_session:
        chunk_repo = PostgresChunkRepository(db_session)
        embedder = HostedEmbeddings(
            provider=settings.embedding_provider,
            api_key=settings.embedding_api_key,
            model=settings.embedding_model,
        )
        reindex = rtc.ReindexTenantChunksUseCase(chunk_repo, embedder)
        for page_key, body in _PAGE_BODIES.items():
            await reindex.execute(cms_page_id=page_ids[page_key], tenant_id=tenant_id, body=body)
        await db_session.commit()

    hits = 0
    reciprocal_ranks: list[float] = []
    latencies: list[float] = []

    async with AsyncSession(engine) as db_session:
        chunk_repo = PostgresChunkRepository(db_session)
        embedder = HostedEmbeddings(
            provider=settings.embedding_provider,
            api_key=settings.embedding_api_key,
            model=settings.embedding_model,
        )
        rag = RAGSearchUseCase(chunk_repo, embedder)

        for row in rows:
            expected_pid = page_ids.get(row["expected_cms_page_id"])
            if expected_pid is None:
                continue
            t0 = time.perf_counter()
            result = await rag.execute(query=row["query"], tenant_id=tenant_id)
            latencies.append((time.perf_counter() - t0) * 1000)

            retrieved = [str(c.cms_page_id) for c in result.chunks]
            if str(expected_pid) in retrieved:
                hits += 1
                reciprocal_ranks.append(1.0 / (retrieved.index(str(expected_pid)) + 1))
            else:
                reciprocal_ranks.append(0.0)

    # Teardown tenant
    async with engine.begin() as conn:
        await conn.execute(text("DELETE FROM tenants WHERE id = :id"), {"id": str(tenant_id)})

    n = len(rows)
    p95_latency = sorted(latencies)[int(0.95 * len(latencies))] if latencies else 0.0
    return {
        "chunker": chunker_name,
        "hit_at_5": hits / n,
        "mrr": sum(reciprocal_ranks) / n,
        "mean_latency_ms": statistics.mean(latencies) if latencies else 0.0,
        "p95_latency_ms": p95_latency,
    }


def _pick_winner(results: list[dict], recall_threshold: float, latency_cap_ms: float = 200.0) -> dict | None:
    eligible = [r for r in results if r["hit_at_5"] >= recall_threshold and r["p95_latency_ms"] <= latency_cap_ms]
    if not eligible:
        return None
    return sorted(eligible, key=lambda r: (-r["hit_at_5"], -r["mrr"], r["mean_latency_ms"]))[0]


@pytest.mark.asyncio
async def test_chunker_bakeoff(eval_engine) -> None:
    engine, settings = eval_engine
    rows = [json.loads(l) for l in GOLDEN.read_text().splitlines() if l.strip()]
    thresholds = yaml.safe_load(THRESHOLDS.read_text())
    recall_threshold = thresholds["rag_golden_set_recall_at_5"]

    results: list[dict] = []
    for name in _CHUNKERS:
        print(f"\nRunning chunker: {name} ...")
        r = await _run_variant(name, rows, engine, settings)
        results.append(r)
        print(f"  hit@5={r['hit_at_5']:.3f}  MRR={r['mrr']:.3f}  mean={r['mean_latency_ms']:.0f}ms  p95={r['p95_latency_ms']:.0f}ms")

    winner = _pick_winner(results, recall_threshold)

    # Build Markdown table
    header = "| chunker | hit@5 | MRR | mean_ms | p95_ms | eligible |"
    sep =    "|---------|-------|-----|---------|--------|----------|"
    table_rows = []
    for r in results:
        eligible = "✓" if r["hit_at_5"] >= recall_threshold and r["p95_latency_ms"] <= 200 else "✗"
        mark = " **← WINNER**" if winner and r["chunker"] == winner["chunker"] else ""
        table_rows.append(
            f"| {r['chunker']}{mark} | {r['hit_at_5']:.3f} | {r['mrr']:.3f} | "
            f"{r['mean_latency_ms']:.0f} | {r['p95_latency_ms']:.0f} | {eligible} |"
        )

    table = "\n".join([header, sep] + table_rows)
    winner_line = f"\n**Winner**: `{winner['chunker']}`" if winner else "\n**Winner**: none (no variant passed the gate)"

    print(f"\n=== Chunker Bake-Off Results ===\n{table}{winner_line}")

    # Append to DECISIONS.md if Entry #1.5 not already populated
    decisions_text = DECISIONS_MD.read_text(encoding="utf-8")
    entry_marker = "## Entry #1.5 — Chunker variant"
    if "To be populated" in decisions_text:
        entry_content = (
            f"\n**Date**: 2026-05-28\n"
            f"**Owner**: B (Agent / RAG)\n"
            f"**Decision**: {winner['chunker'] if winner else 'TBD — no variant passed gate'}\n\n"
            f"### Bake-off results\n\n"
            f"{table}\n"
            f"{winner_line}\n"
            f"\n### Decision rule\n"
            f"Highest `hit@5` satisfying recall ≥ {recall_threshold} AND p95 latency ≤ 200ms.\n"
            f"Ties broken by MRR then lower mean latency.\n"
        )
        new_text = decisions_text.replace(
            "*To be populated by Owner B (T182) after three-way bake-off on 15-triple RAG golden set.*\n\n"
            "Topics to cover: fixed-size baseline (500-token, no overlap) vs. paragraph-aware\n"
            "recursive (400/50/600) vs. header-first recursive (full heading path prepended).\n"
            "Metrics: `hit@5`, `MRR`, mean retrieval latency (ms). Winner = highest `hit@5`\n"
            "satisfying `rag_golden_set_recall_at_5 ≥ 0.85` AND latency ≤ 200ms p95; ties\n"
            "broken by `MRR` then latency.",
            entry_content.strip(),
        )
        DECISIONS_MD.write_text(new_text, encoding="utf-8")
        print(f"  → Appended results to {DECISIONS_MD}")
