"""Unit tests for OriginCheckMiddleware (H1 — server-side origin enforcement)."""

from __future__ import annotations

import asyncio

from app.frameworks.api.middleware.origin_check import OriginCheckMiddleware

_PROTECTED = frozenset({"/widget/config", "/chat"})


def _scope(path: str, origin: str | None = None) -> dict:
    headers: list[tuple[bytes, bytes]] = []
    if origin is not None:
        headers.append((b"origin", origin.encode()))
    return {"type": "http", "method": "GET", "path": path, "headers": headers}


async def _call(mw: OriginCheckMiddleware, scope: dict) -> int:
    captured: list[int] = [200]

    async def receive() -> dict:
        return {"type": "http.request", "body": b""}

    async def send(msg: dict) -> None:
        if msg.get("type") == "http.response.start":
            captured[0] = msg["status"]

    async def downstream(s: dict, r, sd) -> None:
        await sd({"type": "http.response.start", "status": 200, "headers": []})
        await sd({"type": "http.response.body", "body": b""})

    mw.app = downstream  # type: ignore[assignment]
    await mw(scope, receive, send)
    return captured[0]


def test_protected_path_missing_origin_returns_403() -> None:
    mw = OriginCheckMiddleware(app=None, protected_paths=_PROTECTED)  # type: ignore[arg-type]
    assert asyncio.run(_call(mw, _scope("/chat"))) == 403


def test_protected_path_missing_origin_config_returns_403() -> None:
    mw = OriginCheckMiddleware(app=None, protected_paths=_PROTECTED)  # type: ignore[arg-type]
    assert asyncio.run(_call(mw, _scope("/widget/config"))) == 403


def test_protected_path_allowed_origin_passes() -> None:
    async def allow_all(origin: str) -> bool:
        return True

    mw = OriginCheckMiddleware(app=None, origin_lookup=allow_all, protected_paths=_PROTECTED)  # type: ignore[arg-type]
    assert asyncio.run(_call(mw, _scope("/chat", origin="https://allowed.example.com"))) == 200


def test_protected_path_disallowed_origin_returns_403() -> None:
    async def deny_all(origin: str) -> bool:
        return False

    mw = OriginCheckMiddleware(app=None, origin_lookup=deny_all, protected_paths=_PROTECTED)  # type: ignore[arg-type]
    assert asyncio.run(_call(mw, _scope("/chat", origin="https://evil.example.com"))) == 403


def test_unprotected_path_no_origin_passes() -> None:
    mw = OriginCheckMiddleware(app=None, protected_paths=_PROTECTED)  # type: ignore[arg-type]
    assert asyncio.run(_call(mw, _scope("/healthz"))) == 200


def test_unprotected_path_no_origin_widget_token_passes() -> None:
    mw = OriginCheckMiddleware(app=None, protected_paths=_PROTECTED)  # type: ignore[arg-type]
    assert asyncio.run(_call(mw, _scope("/widget/token"))) == 200


def test_non_http_scope_passes_through() -> None:
    mw = OriginCheckMiddleware(app=None, protected_paths=_PROTECTED)  # type: ignore[arg-type]
    ws_scope = {"type": "websocket", "path": "/chat", "headers": []}

    async def _run() -> bool:
        called = [False]

        async def downstream(s, r, sd) -> None:
            called[0] = True

        mw.app = downstream  # type: ignore[assignment]
        await mw(ws_scope, None, None)  # type: ignore[arg-type]
        return called[0]

    assert asyncio.run(_run()) is True


def test_legacy_mode_no_lookup_passes_all() -> None:
    mw = OriginCheckMiddleware(app=None)  # no protected_paths, no lookup  # type: ignore[arg-type]
    assert asyncio.run(_call(mw, _scope("/chat"))) == 200
    assert asyncio.run(_call(mw, _scope("/chat", origin="https://anything.example.com"))) == 200


def test_legacy_mode_with_lookup_blocks_disallowed_present_origin() -> None:
    async def deny_all(origin: str) -> bool:
        return False

    mw = OriginCheckMiddleware(app=None, origin_lookup=deny_all)  # type: ignore[arg-type]
    assert asyncio.run(_call(mw, _scope("/chat", origin="https://evil.example.com"))) == 403


def test_legacy_mode_with_lookup_allows_missing_origin() -> None:
    async def deny_all(origin: str) -> bool:
        return False

    mw = OriginCheckMiddleware(app=None, origin_lookup=deny_all)  # type: ignore[arg-type]
    assert asyncio.run(_call(mw, _scope("/chat"))) == 200
