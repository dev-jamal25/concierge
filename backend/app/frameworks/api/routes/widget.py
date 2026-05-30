"""Minimal widget API routes owned by Slice D."""

from __future__ import annotations

from pathlib import Path
from typing import Any
from uuid import UUID

import jwt
from fastapi import APIRouter, Depends, Header, HTTPException, Response, status
from fastapi.responses import FileResponse, HTMLResponse, PlainTextResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.repositories.tenant_repository import PostgresTenantRepository
from app.adapters.repositories.widget_repository import PostgresWidgetRepository
from app.adapters.tokens.pyjwt_signer import PyJWTSigner
from app.frameworks.api.deps import get_token_signer, manager_db_session
from app.use_cases.get_widget_config import GetWidgetConfigUseCase
from app.use_cases.issue_widget_token import (
    DisabledWidgetError,
    IssueWidgetTokenUseCase,
    OriginNotAllowedError,
    UnknownWidgetError,
)

router = APIRouter(tags=["widget"])
bearer = HTTPBearer(auto_error=False)
_ROUTE_FILE = Path(__file__).resolve()
_WIDGET_DIST_CANDIDATES = (
    _ROUTE_FILE.parents[5] / "widget" / "dist",
    _ROUTE_FILE.parents[4] / "widget" / "dist",
    Path.cwd() / "widget" / "dist",
    Path.cwd().parent / "widget" / "dist",
)
_FALLBACK_WIDGET_JS = """
(function () {
  var script = document.currentScript;
  if (!script) return;
  var widgetId = script.dataset.widgetId;
  if (!widgetId) return;
  var apiBase = script.dataset.apiBase || new URL(script.src).origin;
  var origin = window.location.origin;
  fetch(apiBase + "/widget/token", {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ widget_id: widgetId, origin: origin })
  })
    .then(function (response) {
      if (!response.ok) throw new Error("token");
      return response.json();
    })
    .then(function (issued) {
      return fetch(apiBase + "/widget/config", {
        headers: { authorization: "Bearer " + issued.token }
      }).then(function (response) {
        if (!response.ok) throw new Error("config");
        return response.json().then(function (config) {
          return { token: issued.token, config: config };
        });
      });
    })
    .then(function (bootstrap) {
      var iframe = document.createElement("iframe");
      iframe.src = apiBase + "/widget/?widget_id=" + encodeURIComponent(widgetId);
      iframe.title = "Concierge chat";
      iframe.sandbox.add("allow-scripts", "allow-forms", "allow-same-origin");
      iframe.referrerPolicy = "strict-origin";
      iframe.style.position = "fixed";
      iframe.style.right = "20px";
      iframe.style.bottom = "20px";
      iframe.style.width = "380px";
      iframe.style.height = "560px";
      iframe.style.border = "0";
      iframe.style.zIndex = "2147483647";
      iframe.addEventListener("load", function () {
        iframe.contentWindow.postMessage(
          { type: "concierge.bootstrap", token: bootstrap.token, config: bootstrap.config },
          apiBase
        );
      });
      document.body.appendChild(iframe);
    })
    .catch(function () {
      console.warn("Concierge widget unavailable for this origin");
    });
})();
""".strip()


class WidgetTokenRequest(BaseModel):
    widget_id: str
    origin: str


class WidgetTokenResponse(BaseModel):
    token: str
    expires_in_seconds: int


class WidgetConfigResponse(BaseModel):
    theme_config: dict[str, Any]
    greeting: str
    persona_summary: str
    consent_notice: str


@router.options("/widget/token", include_in_schema=False)
async def widget_token_options(origin: str | None = Header(default=None)) -> Response:
    return _preflight_response(origin, "POST,OPTIONS")


@router.post("/widget/token", response_model=WidgetTokenResponse)
async def issue_widget_token(
    body: WidgetTokenRequest,
    response: Response,
    origin: str | None = Header(default=None),
    session: AsyncSession = Depends(manager_db_session),
    signer: PyJWTSigner = Depends(get_token_signer),
) -> WidgetTokenResponse:
    # Set CORS before the use-case so error responses also carry Access-Control-Allow-Origin.
    # The real origin gate is IssueWidgetTokenUseCase.execute (raises OriginNotAllowedError);
    # CORS is defence-in-depth only, not authentication.
    effective_origin = origin or body.origin
    _allow_origin(response, effective_origin)

    use_case = IssueWidgetTokenUseCase(PostgresWidgetRepository(session), signer)
    try:
        issued = await use_case.execute(widget_public_id=body.widget_id, origin=body.origin)
    except UnknownWidgetError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "unknown widget") from exc
    except (DisabledWidgetError, OriginNotAllowedError) as exc:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "origin not allowed") from exc

    return WidgetTokenResponse(token=issued.token, expires_in_seconds=issued.expires_in_seconds)


@router.options("/widget/config", include_in_schema=False)
async def widget_config_options(origin: str | None = Header(default=None)) -> Response:
    return _preflight_response(origin, "GET,OPTIONS")


@router.get("/widget/config", response_model=WidgetConfigResponse)
async def get_widget_config(
    response: Response,
    origin: str | None = Header(default=None),
    creds: HTTPAuthorizationCredentials | None = Depends(bearer),
    session: AsyncSession = Depends(manager_db_session),
    signer: PyJWTSigner = Depends(get_token_signer),
) -> WidgetConfigResponse:
    # Set CORS early so error responses also carry Access-Control-Allow-Origin.
    if origin is not None:
        _allow_origin(response, origin)

    if creds is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "missing widget token")
    try:
        claims = signer.verify_token(creds.credentials)
    except jwt.PyJWTError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid widget token") from exc

    issued_origin = str(claims["origin"])
    if origin is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "missing origin")
    if origin != issued_origin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "origin mismatch")

    tenant_id = UUID(str(claims["tenant_id"]))
    widgets = PostgresWidgetRepository(session)
    if not await widgets.is_origin_allowed(tenant_id, issued_origin):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "origin not allowed")

    config = await GetWidgetConfigUseCase(PostgresTenantRepository(session)).execute(tenant_id)
    _allow_origin(response, issued_origin)
    return WidgetConfigResponse(
        theme_config=config.theme_config,
        greeting=config.greeting,
        persona_summary=config.persona_summary,
        consent_notice=config.consent_notice,
    )


@router.get("/widget.js", response_class=PlainTextResponse, include_in_schema=False)
async def widget_loader_js() -> Response:
    dist = _widget_dist_dir()
    if dist is not None:
        loader = dist / "widget.js"
        if loader.is_file():
            return FileResponse(loader, media_type="application/javascript")

    return PlainTextResponse(
        _FALLBACK_WIDGET_JS,
        media_type="application/javascript",
    )


@router.get("/widget/assets/{asset_path:path}", include_in_schema=False)
async def widget_asset(asset_path: str) -> FileResponse:
    dist = _widget_dist_dir()
    if dist is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "widget assets not built")

    assets_root = (dist / "assets").resolve()
    asset = (assets_root / asset_path).resolve()
    if not asset.is_file() or assets_root not in asset.parents:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "widget asset not found")
    return FileResponse(asset)


@router.get("/widget/", response_class=HTMLResponse, include_in_schema=False)
async def widget_iframe(
    widget_id: str,
    session: AsyncSession = Depends(manager_db_session),
) -> HTMLResponse:
    frame_ancestors = "'none'"
    widgets = PostgresWidgetRepository(session)
    widget = await widgets.get_by_public_id(widget_id)
    if widget is not None:
        origins = await widgets.list_allowed_origins(widget.tenant_id)
        frame_ancestors = " ".join(origin.origin for origin in origins) or "'none'"

    dist = _widget_dist_dir()
    index = dist / "index.html" if dist is not None else None
    if index is not None and index.is_file():
        response = FileResponse(index, media_type="text/html")
    else:
        response = HTMLResponse(
            "<!doctype html><html><body><div id='root'>Concierge widget</div></body></html>"
        )
    response.headers["Content-Security-Policy"] = f"frame-ancestors {frame_ancestors}"
    return response


def _widget_dist_dir() -> Path | None:
    for candidate in _WIDGET_DIST_CANDIDATES:
        if candidate.is_dir():
            return candidate
    return None


def _preflight_response(origin: str | None, methods: str) -> Response:
    if origin is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "missing origin")
    response = Response(status_code=status.HTTP_204_NO_CONTENT)
    _allow_origin(response, origin)
    response.headers["Access-Control-Allow-Methods"] = methods
    response.headers["Access-Control-Max-Age"] = "300"
    return response


def _allow_origin(response: Response, origin: str) -> None:
    response.headers["Access-Control-Allow-Origin"] = origin
    response.headers["Access-Control-Allow-Headers"] = "authorization,content-type,origin"
    response.headers["Vary"] = "Origin"
