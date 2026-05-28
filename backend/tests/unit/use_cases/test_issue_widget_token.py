from __future__ import annotations

from uuid import uuid4

import pytest

from app.entities.widget import Widget
from app.use_cases.issue_widget_token import (
    IssueWidgetTokenUseCase,
    OriginNotAllowedError,
    UnknownWidgetError,
)


class FakeWidgetRepository:
    def __init__(self, widget: Widget | None, *, allowed: bool = True) -> None:
        self.widget = widget
        self.allowed = allowed

    async def get_by_public_id(self, public_id: str) -> Widget | None:
        if self.widget and self.widget.public_id == public_id:
            return self.widget
        return None

    async def is_origin_allowed(self, tenant_id, origin: str) -> bool:
        return self.allowed


class FakeTokenSigner:
    def sign_token(self, claims, ttl):
        self.claims = claims
        self.ttl = ttl
        return "signed-token"

    def verify_token(self, token: str):
        return self.claims


@pytest.mark.asyncio
async def test_issue_widget_token_contains_expected_claims() -> None:
    widget = Widget(
        id=uuid4(),
        tenant_id=uuid4(),
        public_id="wgt_pub_test",
        is_enabled=True,
    )
    signer = FakeTokenSigner()
    use_case = IssueWidgetTokenUseCase(FakeWidgetRepository(widget), signer)

    issued = await use_case.execute(
        widget_public_id="wgt_pub_test",
        origin="https://acme.example.com",
    )

    assert issued.token == "signed-token"
    assert issued.expires_in_seconds == 300
    assert signer.claims["tenant_id"] == str(widget.tenant_id)
    assert signer.claims["widget_id"] == str(widget.id)
    assert signer.claims["origin"] == "https://acme.example.com"


@pytest.mark.asyncio
async def test_issue_widget_token_rejects_unknown_widget() -> None:
    use_case = IssueWidgetTokenUseCase(FakeWidgetRepository(None), FakeTokenSigner())

    with pytest.raises(UnknownWidgetError):
        await use_case.execute(widget_public_id="missing", origin="https://acme.example.com")


@pytest.mark.asyncio
async def test_issue_widget_token_rejects_disallowed_origin() -> None:
    widget = Widget(id=uuid4(), tenant_id=uuid4(), public_id="wgt_pub_test", is_enabled=True)
    use_case = IssueWidgetTokenUseCase(
        FakeWidgetRepository(widget, allowed=False), FakeTokenSigner()
    )

    with pytest.raises(OriginNotAllowedError):
        await use_case.execute(
            widget_public_id="wgt_pub_test",
            origin="https://evil.example.com",
        )
