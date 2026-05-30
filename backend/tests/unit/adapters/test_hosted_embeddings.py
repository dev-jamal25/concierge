"""Unit tests for HostedEmbeddings retry/backoff behaviour."""

from __future__ import annotations

import pytest
import httpx

from app.adapters.embeddings.hosted_embeddings import HostedEmbeddings


def _make_adapter(transport: httpx.MockTransport) -> HostedEmbeddings:
    return HostedEmbeddings(
        provider="voyage",
        api_key="test-key",
        model="voyage-3",
        client=httpx.AsyncClient(transport=transport),
    )


def _voyage_ok() -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "object": "list",
            "data": [{"object": "embedding", "embedding": [0.1] * 1024}],
        },
    )


def _voyage_429() -> httpx.Response:
    return httpx.Response(429, json={"error": "rate limit exceeded"})


# --- retry behaviour ---


@pytest.mark.asyncio
async def test_retries_on_429_and_succeeds() -> None:
    """A single 429 followed by a 200 should succeed after one retry."""
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        if len(calls) == 1:
            return _voyage_429()
        return _voyage_ok()

    adapter = _make_adapter(httpx.MockTransport(handler))
    result = await adapter.embed(["opening hours"])

    assert len(calls) == 2, f"expected 2 attempts, got {len(calls)}"
    assert len(result) == 1
    assert len(result[0]) == 1024


@pytest.mark.asyncio
async def test_retries_on_5xx_and_succeeds() -> None:
    """A single 503 followed by a 200 should succeed after one retry."""
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        if len(calls) == 1:
            return httpx.Response(503, json={"error": "unavailable"})
        return _voyage_ok()

    adapter = _make_adapter(httpx.MockTransport(handler))
    result = await adapter.embed(["what coffees do you sell?"])

    assert len(calls) == 2
    assert len(result[0]) == 1024


@pytest.mark.asyncio
async def test_raises_after_retry_cap_on_persistent_429() -> None:
    """Persistent 429 across all attempts should raise HTTPStatusError."""
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return _voyage_429()

    adapter = _make_adapter(httpx.MockTransport(handler))
    with pytest.raises(httpx.HTTPStatusError) as exc_info:
        await adapter.embed(["what coffees do you sell?"])

    assert exc_info.value.response.status_code == 429
    assert len(calls) >= 2, "should have retried at least once before giving up"


@pytest.mark.asyncio
async def test_does_not_retry_on_4xx_non_429() -> None:
    """A 401 (bad key) is a permanent error and must NOT be retried."""
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return httpx.Response(401, json={"error": "unauthorized"})

    adapter = _make_adapter(httpx.MockTransport(handler))
    with pytest.raises(httpx.HTTPStatusError):
        await adapter.embed(["hello"])

    assert len(calls) == 1, "non-retryable 4xx should not be retried"


# --- other providers benefit from retry too ---


@pytest.mark.asyncio
async def test_cohere_retries_on_429() -> None:
    """Cohere provider also retries on 429."""
    calls: list[int] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        if len(calls) == 1:
            return _voyage_429()
        return httpx.Response(
            200,
            json={"embeddings": {"float": [[0.2] * 1024]}},
        )

    adapter = HostedEmbeddings(
        provider="cohere",
        api_key="test-key",
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )
    result = await adapter.embed(["hello cohere"])

    assert len(calls) == 2
    assert len(result[0]) == 1024
