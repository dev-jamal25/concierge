"""RAGSearchUseCase (T074) — Layer 2.

1. Embeds the user query.
2. Retrieves top-20 chunks (query-time tenant + published filter).
3. Re-ranks to top-5 via hosted reranker if available; falls back to
   top-5 by cosine score.
4. Returns the top-5 chunks with cms_page_id and content snippet.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

import httpx

from app.entities.chunk import Chunk
from app.use_cases.protocols.chunk_repository import ChunkRepository
from app.use_cases.protocols.embedding_client import EmbeddingClient


@dataclass
class RAGResult:
    chunks: list[Chunk]
    reranked: bool


class RAGSearchUseCase:
    def __init__(
        self,
        chunk_repo: ChunkRepository,
        embedding_client: EmbeddingClient,
        reranker_url: str | None = None,
        reranker_api_key: str | None = None,
        reranker_model: str | None = None,
    ) -> None:
        self._chunks = chunk_repo
        self._embedder = embedding_client
        self._reranker_url = reranker_url
        self._reranker_api_key = reranker_api_key
        self._reranker_model = reranker_model

    async def execute(self, *, query: str, tenant_id: UUID) -> RAGResult:
        vectors = await self._embedder.embed([query])
        candidates = await self._chunks.query(tenant_id=tenant_id, embedding=vectors[0], limit=20)

        if not candidates:
            return RAGResult(chunks=[], reranked=False)

        if self._reranker_url and self._reranker_api_key:
            top5 = await self._rerank(query, candidates)
            return RAGResult(chunks=top5, reranked=True)

        return RAGResult(chunks=candidates[:5], reranked=False)

    async def _rerank(self, query: str, candidates: list[Chunk]) -> list[Chunk]:
        texts = [c.content for c in candidates]
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.post(
                    self._reranker_url,  # type: ignore[arg-type]
                    json={
                        "query": query,
                        "documents": texts,
                        "model": self._reranker_model,
                        "top_n": 5,
                    },
                    headers={"Authorization": f"Bearer {self._reranker_api_key}"},
                )
                resp.raise_for_status()
                results = resp.json()["results"]
                ordered = sorted(results, key=lambda r: r["index"])
                top_indices = [r["index"] for r in sorted(results, key=lambda r: r["relevance_score"], reverse=True)[:5]]
                return [candidates[i] for i in top_indices]
        except Exception:
            # Graceful fallback to top-5 by vector score (T169)
            return candidates[:5]
