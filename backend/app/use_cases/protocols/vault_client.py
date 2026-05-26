"""VaultClient protocol (T032) — Layer 2 interface."""

from __future__ import annotations

from typing import Protocol


class VaultClient(Protocol):
    async def get_secret(self, path: str) -> dict[str, str] | None: ...

    async def set_secret(self, path: str, value: dict[str, str]) -> None: ...

    async def rotate_key(self, key_id: str) -> str:
        """Generate a new key version; return the new key identifier."""
        ...
