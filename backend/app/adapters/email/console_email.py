"""ConsoleEmailSender — v1.0 stub implementing EmailSender.

Logs the invitation link instead of dispatching mail. A real provider adapter
swaps in behind the same protocol later.
"""

from __future__ import annotations

import logging

logger = logging.getLogger("concierge.email")


class ConsoleEmailSender:
    async def send_invitation(self, *, to: str, tenant_name: str, accept_url: str) -> None:
        logger.info("invitation email to=%s tenant=%s url=%s", to, tenant_name, accept_url)
