"""SessionMemory (T190) — Layer 2 use case.

Wraps SessionStore to provide turn-level conversation history.

Key contract:
- Key passed to the store: "{tenant_id}:{conversation_id}"
- Only clean turns stored: dicts with "role" and "content" keys only.
  Tool-call plumbing (tool_use, tool_result roles) is intentionally stripped.
- History is capped at session_max_messages (default 20). Oldest turns are
  dropped first when the cap is reached.
- PII redaction is Owner C's upstream concern; this class stores verbatim.
"""

from __future__ import annotations

from uuid import UUID

from app.use_cases.protocols.session_store import SessionStore

_CLEAN_ROLES = {"user", "assistant"}


class SessionMemory:
    def __init__(
        self,
        store: SessionStore,
        *,
        ttl: int = 3600,
        max_messages: int = 20,
    ) -> None:
        self._store = store
        self._ttl = ttl
        self._max = max_messages

    def _key(self, tenant_id: UUID, conversation_id: UUID) -> str:
        return f"{tenant_id}:{conversation_id}"

    async def load(
        self, tenant_id: UUID, conversation_id: UUID
    ) -> list[dict[str, str]]:
        """Return stored clean turns, newest-last. Empty list if no prior history."""
        raw = await self._store.retrieve(self._key(tenant_id, conversation_id))
        if not isinstance(raw, list):
            return []
        return raw

    async def append_turn(
        self,
        tenant_id: UUID,
        conversation_id: UUID,
        user_message: str,
        assistant_reply: str,
    ) -> None:
        """Append the current turn and persist, dropping oldest if over cap."""
        key = self._key(tenant_id, conversation_id)
        history: list[dict[str, str]] = await self.load(tenant_id, conversation_id)

        history.append({"role": "user", "content": user_message})
        history.append({"role": "assistant", "content": assistant_reply})

        if len(history) > self._max:
            history = history[len(history) - self._max :]

        await self._store.store(key, history, ttl=self._ttl)
