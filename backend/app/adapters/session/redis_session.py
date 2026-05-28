"""RedisSession (T046) — Layer 3 adapter implementing SessionStore.

Stub for Phase 2; full implementation in Slice B / US1.
Backed by Redis 7. Keys are namespaced as "session:<key>" so they're
bulk-deletable per tenant during erasure (T110 scans "session:*").

Values are JSON-serialised so any JSON-safe type survives a round-trip.
"""

from __future__ import annotations

import json
from typing import Any

import redis.asyncio as aioredis

from app.use_cases.protocols.session_store import SessionStore


class RedisSession:
    """Implements use_cases.protocols.session_store.SessionStore."""

    _PREFIX = "session:"

    def __init__(self, *, redis_url: str) -> None:
        self._redis: aioredis.Redis = aioredis.from_url(
            redis_url, encoding="utf-8", decode_responses=True
        )

    def _key(self, key: str) -> str:
        return f"{self._PREFIX}{key}"

    async def store(self, key: str, value: Any, ttl: int) -> None:
        await self._redis.set(self._key(key), json.dumps(value), ex=ttl)

    async def retrieve(self, key: str) -> Any | None:
        raw = await self._redis.get(self._key(key))
        if raw is None:
            return None
        return json.loads(raw)

    async def delete(self, key: str) -> None:
        await self._redis.delete(self._key(key))


def make_redis_session(redis_url: str) -> SessionStore:
    return RedisSession(redis_url=redis_url)
