"""SessionStore protocol (T029) — Layer 2 interface.

Owner B publishes this seam. The concrete adapter (RedisSession) lives in
adapters/session/; backed by Redis 7 with per-key TTL.

Keys are namespaced as "session:<key>" by the adapter; callers pass bare keys.
"""

from __future__ import annotations

from typing import Any, Protocol


class SessionStore(Protocol):
    async def store(self, key: str, value: Any, ttl: int) -> None:
        """Persist value under key for ttl seconds."""
        ...

    async def retrieve(self, key: str) -> Any | None:
        """Return stored value or None if missing / expired."""
        ...

    async def delete(self, key: str) -> None: ...
