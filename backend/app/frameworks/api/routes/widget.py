"""Minimal widget API routes owned by Slice D."""

from __future__ import annotations

from typing import Any
from uuid import UUID

import jwt
from fastapi import APIRouter, Depends, Header, HTTPException, Response, status
from fastapi.responses import HTMLResponse, PlainTextResponse
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


@router.post("/widget/token", response_model=WidgetTokenResponse)
async def issue_widget_token(
    body: WidgetTokenRequest,
    response: Response,
    session: AsyncSession = Depends(manager_db_session),
    signer: PyJWTSigner = Depends(get_token_signer),
) -> WidgetTokenResponse:
    use_case = IssueWidgetTokenUseCase(PostgresWidgetRepository(session), signer)
    try:
        issued = await use_case.execute(widget_public_id=body.widget_id, origin=body.origin)
    except UnknownWidgetError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "unknown widget") from exc
    except (DisabledWidgetError, OriginNotAllowedError) as exc:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "origin not allowed") from exc

    _allow_origin(response, body.origin)
    return WidgetTokenResponse(token=issued.token, expires_in_seconds=issued.expires_in_seconds)


@router.get("/widget/config", response_model=WidgetConfigResponse)
async def get_widget_config(
    response: Response,
    origin: str | None = Header(default=None),
    creds: HTTPAuthorizationCredentials | None = Depends(bearer),
    session: AsyncSession = Depends(manager_db_session),
    signer: PyJWTSigner = Depends(get_token_signer),
) -> WidgetConfigResponse:
    if creds is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "missing widget token")
    try:
        claims = signer.verify_token(creds.credentials)
    except jwt.PyJWTError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid widget token") from exc

    issued_origin = str(claims["origin"])
    if origin is not None and origin != issued_origin:
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
async def widget_loader_js() -> PlainTextResponse:
    return PlainTextResponse(
        'console.info("Concierge widget loader route is ready");',
        media_type="application/javascript",
    )


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

    response = HTMLResponse("<!doctype html><div id='root'>Concierge widget</div>")
    response.headers["Content-Security-Policy"] = f"frame-ancestors {frame_ancestors}"
    return response


def _allow_origin(response: Response, origin: str) -> None:
    response.headers["Access-Control-Allow-Origin"] = origin
    response.headers["Access-Control-Allow-Headers"] = "authorization,content-type,origin"
    response.headers["Vary"] = "Origin"
