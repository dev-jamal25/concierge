"""HostedEmbeddings (T045) — Layer 3 adapter implementing EmbeddingClient.

Stub for Phase 2; provider selection and full implementation in Slice B / US1.
Provider is chosen via EMBEDDING_PROVIDER env var (voyage | cohere | openai).
Vector dimension is 1024 — documented in data-model.md and DECISIONS.md entry 2.
"""

from __future__ import annotations

import httpx

from app.use_cases.protocols.embedding_client import EmbeddingClient


class HostedEmbeddings:
    """Implements use_cases.protocols.embedding_client.EmbeddingClient."""

    def __init__(
        self,
        *,
        provider: str,
        api_key: str,
        model: str | None = None,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._provider = provider.lower()
        self._api_key = api_key
        self._model = model
        self._http = client or httpx.AsyncClient(timeout=30.0)

    async def embed(self, texts: list[str]) -> list[list[float]]:
        if self._provider == "voyage":
            return await self._embed_voyage(texts)
        if self._provider == "cohere":
            return await self._embed_cohere(texts)
        if self._provider == "openai":
            return await self._embed_openai(texts)
        raise ValueError(f"Unknown embedding provider: {self._provider!r}")

    async def _embed_voyage(self, texts: list[str]) -> list[list[float]]:
        model = self._model or "voyage-3"
        resp = await self._http.post(
            "https://api.voyageai.com/v1/embeddings",
            json={"input": texts, "model": model},
            headers={"Authorization": f"Bearer {self._api_key}"},
        )
        resp.raise_for_status()
        data = resp.json()
        return [item["embedding"] for item in data["data"]]

    async def _embed_cohere(self, texts: list[str]) -> list[list[float]]:
        model = self._model or "embed-english-v3.0"
        resp = await self._http.post(
            "https://api.cohere.com/v2/embed",
            json={"texts": texts, "model": model, "input_type": "search_document"},
            headers={"Authorization": f"Bearer {self._api_key}"},
        )
        resp.raise_for_status()
        data = resp.json()
        return data["embeddings"]["float"]

    async def _embed_openai(self, texts: list[str]) -> list[list[float]]:
        model = self._model or "text-embedding-3-large"
        resp = await self._http.post(
            "https://api.openai.com/v1/embeddings",
            json={"input": texts, "model": model},
            headers={"Authorization": f"Bearer {self._api_key}"},
        )
        resp.raise_for_status()
        data = resp.json()
        return [item["embedding"] for item in data["data"]]


def make_hosted_embeddings(
    provider: str,
    api_key: str,
    model: str | None = None,
) -> EmbeddingClient:
    return HostedEmbeddings(provider=provider, api_key=api_key, model=model)
