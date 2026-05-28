"""SessionStore protocol (T029, T191) — Layer 2 interface.

Owner B publishes this seam. The concrete adapter (RedisSession) lives in
adapters/session/; backed by Redis 7 with per-key TTL.

Key schema (T191): session:{tenant_id}:{conversation_id} — callers pass
"{tenant_id}:{conversation_id}" as the bare key so the adapter can namespace
and Owner A can purge one tenant's keys via delete_by_tenant.
"""

from __future__ import annotations

from typing import Any, Protocol
from uuid import UUID


class SessionStore(Protocol):
    async def store(self, key: str, value: Any, ttl: int) -> None:
        """Persist value under key with a fixed expiry of ttl seconds.

        First write: SET NX EX ttl (creates the key and sets the clock once).
        Subsequent writes: SET KEEPTTL (preserves the original expiry — fixed TTL,
        not sliding).
        """
        ...

    async def retrieve(self, key: str) -> Any | None:
        """Return stored value or None if missing / expired."""
        ...

    async def delete(self, key: str) -> None: ...

    async def delete_by_tenant(self, tenant_id: UUID) -> None:
        """Delete all session keys belonging to tenant_id (T191 erasure seam).

        Published for Owner A's T129. Scans session:{tenant_id}:* and deletes
        in a pipeline. Does not raise if no keys exist.
        """
        ...
