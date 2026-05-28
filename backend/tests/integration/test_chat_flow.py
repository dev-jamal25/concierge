"""Chat flow integration test (T092).

Seeds a tenant with 2 published CMS pages and an embedding stub, then runs
a full chat turn end-to-end through all use-case layers (no HTTP — calls the
use cases directly with real DB). Asserts:
  - route=faq when classifier returns faq label
  - retrieved_chunks is non-empty and content comes from the seeded pages
  - chunks from the other tenant are NOT returned (RLS gate)
  - full round-trip completes within 5s (SC-006)

Uses zero-vector embeddings (bypasses real embedding API) so the test runs
without any external API keys. RLS is enforced by the concierge_app role.

Run:
    pytest tests/integration/test_chat_flow.py -m integration
"""

from __future__ import annotations

import time
import uuid
from uuid import UUID

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]

TENANT_A = uuid.uuid4()
TENANT_B = uuid.uuid4()
WIDGET_A = uuid.uuid4()
WIDGET_B = uuid.uuid4()
PAGE_A1 = uuid.uuid4()
PAGE_A2 = uuid.uuid4()
PAGE_B1 = uuid.uuid4()

_PAGE_A1_CONTENT = "Our refund policy allows returns within 30 days with original receipt."
_PAGE_A2_CONTENT = "We are open Monday to Friday 9am to 6pm. Saturday by appointment only."
_PAGE_B1_CONTENT = "Tenant B proprietary information — must not leak to Tenant A."

_ZERO_VEC = "[" + ",".join(["0.1"] * 1024) + "]"


# ---------------------------------------------------------------------------
# Seeding
# ---------------------------------------------------------------------------


async def _seed(engine) -> None:
    async with engine.begin() as conn:
        for tid, slug in (
            (TENANT_A, f"chat-flow-a-{TENANT_A.hex[:6]}"),
            (TENANT_B, f"chat-flow-b-{TENANT_B.hex[:6]}"),
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
        for pid, tid, slug, content in (
            (PAGE_A1, TENANT_A, f"refund-{PAGE_A1.hex[:6]}", _PAGE_A1_CONTENT),
            (PAGE_A2, TENANT_A, f"hours-{PAGE_A2.hex[:6]}", _PAGE_A2_CONTENT),
            (PAGE_B1, TENANT_B, f"secret-{PAGE_B1.hex[:6]}", _PAGE_B1_CONTENT),
        ):
            await conn.execute(
                text(
                    "INSERT INTO cms_pages (id, tenant_id, title, body, state, slug) "
                    "VALUES (:id, :tid, :title, :body, 'published', :slug) ON CONFLICT DO NOTHING"
                ),
                {"id": str(pid), "tid": str(tid), "title": slug, "body": content, "slug": slug},
            )
        # Seed chunks with near-identical vectors so any query hits them
        for i, (pid, tid, content) in enumerate([
            (PAGE_A1, TENANT_A, _PAGE_A1_CONTENT),
            (PAGE_A2, TENANT_A, _PAGE_A2_CONTENT),
            (PAGE_B1, TENANT_B, _PAGE_B1_CONTENT),
        ]):
            await conn.execute(
                text(
                    "INSERT INTO chunks (id, tenant_id, cms_page_id, chunk_index, content, embedding) "
                    "VALUES (gen_random_uuid(), :tid, :pid, 0, :content, :emb::vector) ON CONFLICT DO NOTHING"
                ),
                {"tid": str(tid), "pid": str(pid), "content": content, "emb": _ZERO_VEC},
            )


@pytest_asyncio.fixture(scope="module", autouse=True)
async def seed(owner_engine):
    await _seed(owner_engine)


# ---------------------------------------------------------------------------
# Stub classifier that always returns faq with high confidence
# ---------------------------------------------------------------------------


class _FaqClassifier:
    async def classify(self, *, message: str, tenant_id: UUID):
        from dataclasses import dataclass

        @dataclass
        class _R:
            label: str = "faq"
            confidence: float = 0.95
            per_class: dict = None

            def __post_init__(self):
                if self.per_class is None:
                    self.per_class = {"faq": 0.95}

        return _R()


class _ZeroEmbeddings:
    """Returns zero-ish vectors so cosine similarity against seeded chunks is non-zero."""

    async def embed(self, texts: list[str]) -> list[list[float]]:
        return [[0.1] * 1024 for _ in texts]


class _NullSessionStore:
    async def store(self, key, value, ttl): pass
    async def retrieve(self, key): return None
    async def delete(self, key): pass
    async def delete_by_tenant(self, tenant_id): pass


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_faq_route_returns_chunks_from_tenant_a(app_engine) -> None:
    """Chat turn for Tenant A returns chunks; response time < 5s; no Tenant B chunks."""
    from app.adapters.repositories.chunk_repository import PostgresChunkRepository
    from app.adapters.repositories.conversation_repository import PostgresConversationRepository
    from app.use_cases.classify_message import ClassifyMessageUseCase
    from app.use_cases.rag_search import RAGSearchUseCase

    async with AsyncSession(app_engine) as session:
        # Set RLS context to Tenant A
        await session.execute(text(f"SET LOCAL app.tenant_id = '{TENANT_A}'"))

        chunk_repo = PostgresChunkRepository(session)
        conv_repo = PostgresConversationRepository(session)
        embedder = _ZeroEmbeddings()

        classify_uc = ClassifyMessageUseCase(_FaqClassifier())
        rag_uc = RAGSearchUseCase(chunk_repo, embedder)

        conversation_id = uuid.uuid4()
        await conv_repo.create(
            tenant_id=TENANT_A,
            widget_id=WIDGET_A,
            visitor_session=str(conversation_id),
        )

        t0 = time.perf_counter()

        classify_result = await classify_uc.execute(message="What is your refund policy?", tenant_id=TENANT_A)
        assert classify_result.label == "faq"

        rag_result = await rag_uc.execute(query="refund policy", tenant_id=TENANT_A)

        elapsed = time.perf_counter() - t0

        # Assertions
        assert len(rag_result.chunks) > 0, "Expected at least one chunk for Tenant A"
        assert elapsed < 5.0, f"Round-trip took {elapsed:.2f}s — exceeds SC-006 5s SLA"

        # All returned chunks must belong to Tenant A
        for chunk in rag_result.chunks:
            assert str(chunk.tenant_id) == str(TENANT_A), (
                f"RLS leak: chunk {chunk.id} belongs to {chunk.tenant_id}, not Tenant A"
            )

        # Content from Tenant B must not appear
        all_content = " ".join(c.content for c in rag_result.chunks)
        assert "Tenant B proprietary" not in all_content, "Cross-tenant content leak detected"


@pytest.mark.asyncio
async def test_tenant_b_chunks_not_visible_from_tenant_a(app_engine) -> None:
    """Chunks seeded for Tenant B are invisible when queried as Tenant A (RLS gate)."""
    from app.adapters.repositories.chunk_repository import PostgresChunkRepository
    from app.use_cases.rag_search import RAGSearchUseCase

    async with AsyncSession(app_engine) as session:
        await session.execute(text(f"SET LOCAL app.tenant_id = '{TENANT_A}'"))

        rag_uc = RAGSearchUseCase(PostgresChunkRepository(session), _ZeroEmbeddings())
        result = await rag_uc.execute(query="secret proprietary", tenant_id=TENANT_A)

        page_ids = {str(c.cms_page_id) for c in result.chunks}
        assert str(PAGE_B1) not in page_ids, f"Tenant B page {PAGE_B1} leaked to Tenant A query"
