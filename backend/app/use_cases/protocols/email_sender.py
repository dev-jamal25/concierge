"""EmailSender protocol — the external email service seam (stubbed in v1.0)."""

from __future__ import annotations

from typing import Protocol


class EmailSender(Protocol):
    async def send_invitation(self, *, to: str, tenant_name: str, accept_url: str) -> None: ...
