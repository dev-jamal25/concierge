"""OriginCheckMiddleware (T034).

Validates the HTTP Origin header for browser-facing widget/chat/config routes.

Two modes:
- Path-scoped (protected_paths provided): enforces Origin header presence for
  listed paths; missing → 403. If origin_lookup is also provided, disallowed → 403.
  All other paths pass through unconditionally.
- Legacy global (no protected_paths): inert unless origin_lookup is provided,
  and then only blocks requests whose Origin is present but not allowed (original
  stub behaviour, preserved for backward compatibility).

CORS/CSP headers are handled separately by the route handlers. This middleware is
an auth-adjacent server-side guard — it does not replace token verification.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable

from starlette.datastructures import Headers
from starlette.responses import PlainTextResponse
from starlette.types import ASGIApp, Receive, Scope, Send

# (origin) -> is_allowed
OriginLookup = Callable[[str], Awaitable[bool]]


class OriginCheckMiddleware:
    def __init__(
        self,
        app: ASGIApp,
        origin_lookup: OriginLookup | None = None,
        protected_paths: frozenset[str] | None = None,
    ) -> None:
        self.app = app
        self.origin_lookup = origin_lookup
        self._protected: frozenset[str] = protected_paths or frozenset()

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path: str = scope.get("path", "")
        origin = Headers(scope=scope).get("origin")

        if self._protected:
            if path in self._protected:
                if origin is None:
                    await _deny(scope, receive, send)
                    return
                if self.origin_lookup is not None and not await self.origin_lookup(origin):
                    await _deny(scope, receive, send)
                    return
            # Path not in protected set — pass through.
        else:
            # Legacy global mode: only block present-but-disallowed origins.
            if self.origin_lookup is not None and origin is not None:
                if not await self.origin_lookup(origin):
                    await _deny(scope, receive, send)
                    return

        await self.app(scope, receive, send)


async def _deny(scope: Scope, receive: Receive, send: Send) -> None:
    await PlainTextResponse("forbidden", status_code=403)(scope, receive, send)
