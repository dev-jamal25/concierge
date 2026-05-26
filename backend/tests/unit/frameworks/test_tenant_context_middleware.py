"""Unit tests for TenantContextMiddleware (Phase 2 TDD).

Verifies: (1) tenant/user context is derived from the verified token, (2) context
is reset after the response, (3) a tenant_id supplied via body/header/query is
ignored — only the token drives context (correction #4).
"""

from __future__ import annotations

import asyncio

from app.frameworks.api.middleware.tenant_context import TenantContextMiddleware
from app.frameworks.db.session import tenant_id_ctx, user_id_ctx

TOKEN_TENANT = "11111111-1111-1111-1111-111111111111"
TOKEN_USER = "22222222-2222-2222-2222-222222222222"
SPOOF_TENANT = "99999999-9999-9999-9999-999999999999"


def _verifier(token: str) -> dict[str, str]:
    assert token == "good-token"
    return {"tenant_id": TOKEN_TENANT, "sub": TOKEN_USER}


def _scope(headers: list[tuple[bytes, bytes]], query: bytes = b"") -> dict:
    return {
        "type": "http",
        "method": "POST",
        "path": "/chat",
        "query_string": query,
        "headers": headers,
    }


async def _run(mw: TenantContextMiddleware, scope: dict, captured: dict) -> None:
    async def receive() -> dict:
        # Body claims a *different* tenant — must be ignored by the middleware.
        return {"type": "http.request", "body": b'{"tenant_id": "%s"}' % SPOOF_TENANT.encode()}

    async def send(message: dict) -> None:
        pass

    async def downstream(s, r, sd) -> None:
        captured["tenant"] = tenant_id_ctx.get()
        captured["user"] = user_id_ctx.get()

    mw.app = downstream  # type: ignore[assignment]
    await mw(scope, receive, send)


def test_context_derived_from_verified_token() -> None:
    mw = TenantContextMiddleware(app=None, token_verifier=_verifier)  # type: ignore[arg-type]
    captured: dict = {}
    scope = _scope([(b"authorization", b"Bearer good-token")])
    asyncio.run(_run(mw, scope, captured))
    assert captured["tenant"] == TOKEN_TENANT
    assert captured["user"] == TOKEN_USER
    # Reset after response.
    assert tenant_id_ctx.get() is None
    assert user_id_ctx.get() is None


def test_body_and_header_tenant_id_ignored() -> None:
    mw = TenantContextMiddleware(app=None, token_verifier=_verifier)  # type: ignore[arg-type]
    captured: dict = {}
    # Attacker supplies a spoofed tenant via custom header and query string too.
    scope = _scope(
        [
            (b"authorization", b"Bearer good-token"),
            (b"x-tenant-id", SPOOF_TENANT.encode()),
        ],
        query=f"tenant_id={SPOOF_TENANT}".encode(),
    )
    asyncio.run(_run(mw, scope, captured))
    # Only the token's tenant wins.
    assert captured["tenant"] == TOKEN_TENANT
    assert captured["tenant"] != SPOOF_TENANT


def test_no_token_yields_no_context() -> None:
    mw = TenantContextMiddleware(app=None, token_verifier=_verifier)  # type: ignore[arg-type]
    captured: dict = {}
    asyncio.run(_run(mw, _scope([]), captured))
    assert captured["tenant"] is None
    assert captured["user"] is None


def test_invalid_token_yields_no_context() -> None:
    mw = TenantContextMiddleware(app=None, token_verifier=_verifier)  # type: ignore[arg-type]
    captured: dict = {}
    scope = _scope([(b"authorization", b"Bearer bad-token")])
    asyncio.run(_run(mw, scope, captured))
    assert captured["tenant"] is None
