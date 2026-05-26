"""FastAPI application (T012 — [ALL] skeleton).

Owner A wires the tenant_context + origin_check middleware and the manager/auth
routers here as those land. Other slices register their routers via the same
create_app() factory.
"""

from __future__ import annotations

from fastapi import FastAPI


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
    from app.frameworks.api.middleware.tenant_context import TenantContextMiddleware

    app.add_middleware(TenantContextMiddleware)

    # --- Routers (registered as slices land) ---
    from app.frameworks.api.routes import auth as auth_routes
    from app.frameworks.api.routes import manager as manager_routes
    from app.frameworks.api.routes import widget as widget_routes

    app.include_router(auth_routes.router)
    app.include_router(manager_routes.router)
    app.include_router(widget_routes.router)

    return app


app = create_app()
