"""FastAPI application (T012 — [ALL] skeleton).

Owner A wires the tenant_context + origin_check middleware and the manager/auth
routers here as those land. Other slices register their routers via the same
create_app() factory.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from fastapi import FastAPI


def _make_session_token_verifier():
    """Return a token_verifier for TenantContextMiddleware that handles session JWTs.

    Session tokens (HS256, issued by /auth/login) carry tenant_id for tenant_admin
    principals. This lets TenantContextMiddleware set the tenant_id ContextVar for
    all tenant-scoped routes (CMS, leads, chat) when called from the admin UI, not
    just from the widget flow (which uses Ed25519 widget JWTs).

    The verifier is intentionally lenient: any exception → returns None → middleware
    sets no context. Widget JWTs (Ed25519) will fail HS256 decoding and return None,
    which is correct because widget context is resolved separately in route deps.
    """
    from app.frameworks.api.session_auth import decode_session_token

    def _verify(token: str) -> Mapping[str, Any] | None:
        try:
            principal = decode_session_token(token)
        except Exception:
            return None
        if principal.tenant_id is None:
            return {}
        return {"tenant_id": principal.tenant_id, "sub": principal.user_id}

    return _verify


def create_app() -> FastAPI:
    app = FastAPI(title="Concierge API", version="0.1.0")

    @app.get("/healthz", tags=["health"])
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/readyz", tags=["health"])
    async def readyz() -> dict[str, str]:
        # Owner A/D extend this to probe DB/Vault readiness.
        return {"status": "ready"}

    # --- Middleware (registered in Phase 2; outermost first) ---
    from app.frameworks.api.deps import get_guardrails_client
    from app.frameworks.api.middleware.origin_check import OriginCheckMiddleware
    from app.frameworks.api.middleware.pii_redaction import PIIRedactionMiddleware
    from app.frameworks.api.middleware.tenant_context import TenantContextMiddleware

    app.add_middleware(PIIRedactionMiddleware, guardrails=get_guardrails_client())
    # Pass a session-token verifier so the middleware sets tenant_id_ctx for
    # admin-panel requests (session JWT) in addition to widget requests (widget JWT
    # handled separately in get_current_widget_context). Without this the middleware
    # was inert for admin routes, leaving tenant_id_ctx=None and RLS blocking queries.
    app.add_middleware(TenantContextMiddleware, token_verifier=_make_session_token_verifier())
    # OriginCheckMiddleware is outermost: added last so it runs before TenantContext.
    # Route-level deps perform the tenant-aware DB lookup; the middleware enforces
    # that the Origin header is present at all for protected browser-facing routes.
    app.add_middleware(
        OriginCheckMiddleware,
        protected_paths=frozenset({"/widget/config", "/chat"}),
    )

    # --- Routers (registered as slices land) ---
    from app.frameworks.api.routes import admin as admin_routes
    from app.frameworks.api.routes import auth as auth_routes
    from app.frameworks.api.routes import chat as chat_routes
    from app.frameworks.api.routes import cms as cms_routes
    from app.frameworks.api.routes import leads as leads_routes
    from app.frameworks.api.routes import manager as manager_routes
    from app.frameworks.api.routes import widget as widget_routes

    app.include_router(auth_routes.router)
    app.include_router(chat_routes.router)
    app.include_router(cms_routes.router)
    app.include_router(leads_routes.router)
    app.include_router(manager_routes.router)
    app.include_router(widget_routes.router)
    app.include_router(admin_routes.router)

    return app


app = create_app()
