"""TenantContextMiddleware (T033) — Layer 4.

Derives tenant context **only** from a verified bearer token (correction #4):
it never inspects the request body, query string, or arbitrary headers for a
tenant_id. The verified token's claims are written to ContextVars that the DB
session dependency turns into a transaction-local `app.tenant_id` GUC, which RLS
policies enforce. Context is always reset at the end of the request.

Token verification itself is owned by another slice (Owner D's TokenSigner, T030)
for the widget path; this middleware accepts the verifier as an injected callable
so Owner A does not implement D's code. When no verifier is configured (e.g. the
admin/manager surface, which sets context via auth dependencies), the bearer path
is inert.

Implemented as pure ASGI middleware so ContextVars set here are reliably visible
to downstream endpoints and the DB session.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from starlette.datastructures import Headers
from starlette.types import ASGIApp, Receive, Scope, Send

from app.frameworks.db.session import (
    reset_tenant_id,
    reset_user_id,
    set_tenant_id,
    set_user_id,
)

TokenVerifier = Callable[[str], Mapping[str, Any]]


class TenantContextMiddleware:
    def __init__(self, app: ASGIApp, token_verifier: TokenVerifier | None = None) -> None:
        self.app = app
        self.token_verifier = token_verifier

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or self.token_verifier is None:
            await self.app(scope, receive, send)
            return

        claims = self._claims_from_bearer(Headers(scope=scope))
        tenant_token = user_token = None
        if claims is not None:
            tid = claims.get("tenant_id")
            uid = claims.get("sub") or claims.get("user_id")
            if tid is not None:
                tenant_token = set_tenant_id(str(tid))
            if uid is not None:
                user_token = set_user_id(str(uid))

        try:
            await self.app(scope, receive, send)
        finally:
            if tenant_token is not None:
                reset_tenant_id(tenant_token)
            if user_token is not None:
                reset_user_id(user_token)

    def _claims_from_bearer(self, headers: Headers) -> Mapping[str, Any] | None:
        auth = headers.get("authorization")
        if not auth or not auth.lower().startswith("bearer "):
            return None
        token = auth.split(" ", 1)[1].strip()
        try:
            return self.token_verifier(token)  # type: ignore[misc]
        except Exception:
            # An invalid/expired token yields no tenant context; downstream
            # authorization will reject the request.
            return None
