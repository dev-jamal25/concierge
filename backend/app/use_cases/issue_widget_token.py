"""Issue short-lived widget JWTs for allowed origins."""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import timedelta

from app.use_cases.protocols.token_signer import TokenSigner
from app.use_cases.protocols.widget_repository import WidgetRepository


class UnknownWidgetError(Exception):
    pass


class DisabledWidgetError(Exception):
    pass


class OriginNotAllowedError(Exception):
    pass


@dataclass(frozen=True, slots=True)
class IssuedWidgetToken:
    token: str
    expires_in_seconds: int


class IssueWidgetTokenUseCase:
    def __init__(
        self,
        widgets: WidgetRepository,
        token_signer: TokenSigner,
        ttl_seconds: int = 300,
    ) -> None:
        self._widgets = widgets
        self._token_signer = token_signer
        self._ttl_seconds = min(ttl_seconds, 300)

    async def execute(self, *, widget_public_id: str, origin: str) -> IssuedWidgetToken:
        widget = await self._widgets.get_by_public_id(widget_public_id)
        if widget is None:
            raise UnknownWidgetError(widget_public_id)
        if not widget.is_enabled:
            raise DisabledWidgetError(widget_public_id)
        if not await self._widgets.is_origin_allowed(widget.tenant_id, origin):
            raise OriginNotAllowedError(origin)

        token = self._token_signer.sign_token(
            {
                "sub": widget.public_id,
                "tenant_id": str(widget.tenant_id),
                "widget_id": str(widget.id),
                "origin": origin,
                "visitor_session": secrets.token_urlsafe(24),
            },
            ttl=timedelta(seconds=self._ttl_seconds),
        )
        return IssuedWidgetToken(token=token, expires_in_seconds=self._ttl_seconds)
