"""OriginCheckMiddleware (T034) — STUB.

Validates the request Origin against the tenant's allowed_origins (exact-string,
no wildcards). Owner A publishes the stub; the real DB-backed wiring is Owner D's
job (T102), which injects an async origin lookup. Until a lookup is configured the
middleware is inert (does not block requests).
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from starlette.datastructures import Headers
from starlette.responses import PlainTextResponse
from starlette.types import ASGIApp, Receive, Scope, Send

# (tenant_id_or_widget_id, origin) -> is_allowed. Owner D supplies the real one.
OriginLookup = Callable[[str], Awaitable[bool]]


class OriginCheckMiddleware:
    def __init__(self, app: ASGIApp, origin_lookup: OriginLookup | None = None) -> None:
        self.app = app
        self.origin_lookup = origin_lookup

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or self.origin_lookup is None:
            await self.app(scope, receive, send)
            return

        origin = Headers(scope=scope).get("origin")
        if origin is not None and not await self.origin_lookup(origin):
            await PlainTextResponse("origin not allowed", status_code=403)(scope, receive, send)
            return

        await self.app(scope, receive, send)
