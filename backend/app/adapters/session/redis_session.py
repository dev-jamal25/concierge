"""RedisSession (T046, T184, T191) — Layer 3 adapter implementing SessionStore.

Key schema (T191): session:{tenant_id}:{conversation_id}
  Callers pass "{tenant_id}:{conversation_id}" as the bare key.
  Owner A's T129 calls delete_by_tenant to purge one tenant during erasure.

Fixed TTL (T184): the expiry clock starts on first write and is never reset.
  First write:  SET key val NX EX <ttl>  (create with ttl; no-op if key exists)
  Update write: SET key val KEEPTTL      (overwrite value; preserve existing TTL)
  If NX fails (key already present) we fall through to KEEPTTL so the value
  is always written, the TTL is never extended.

Values are JSON-serialised so any JSON-safe type survives a round-trip.
"""

from __future__ import annotations

import json
from typing import Any
from uuid import UUID

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
        full_key = self._key(key)
        serialised = json.dumps(value)
        # Try to create with fixed TTL; if key already exists NX returns None.
        created = await self._redis.set(full_key, serialised, nx=True, ex=ttl)
        if not created:
            # Key exists — overwrite value while preserving the original TTL.
            await self._redis.set(full_key, serialised, keepttl=True)

    async def retrieve(self, key: str) -> Any | None:
        raw = await self._redis.get(self._key(key))
        if raw is None:
            return None
        return json.loads(raw)

    async def delete(self, key: str) -> None:
        await self._redis.delete(self._key(key))

    async def delete_by_tenant(self, tenant_id: UUID) -> None:
        """Delete all session keys for one tenant (T191 erasure seam for Owner A T129)."""
        pattern = f"{self._PREFIX}{tenant_id}:*"
        keys = [k async for k in self._redis.scan_iter(pattern)]
        if keys:
            async with self._redis.pipeline(transaction=False) as pipe:
                for k in keys:
                    pipe.delete(k)
                await pipe.execute()


def make_redis_session(redis_url: str) -> SessionStore:
    return RedisSession(redis_url=redis_url)
