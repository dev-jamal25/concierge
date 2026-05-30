"""Unit tests for PostgresConversationRepository."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app.adapters.repositories.conversation_repository import PostgresConversationRepository


@pytest.mark.asyncio
async def test_create_uses_provided_conversation_id() -> None:
    """create() with an explicit conversation_id must use it as the row PK.

    Without this, agent_turn escalation looks up the client UUID but finds
    no matching row (server-generated UUID differs), raising LookupError → 503.
    """
    expected_id = uuid4()
    added_models: list = []

    session = MagicMock()
    session.add = MagicMock(side_effect=lambda m: added_models.append(m))
    session.flush = AsyncMock()
    session.refresh = AsyncMock()

    repo = PostgresConversationRepository(session)
    with patch("app.adapters.repositories.conversation_repository._to_entity") as mock_entity:
        mock_entity.return_value = MagicMock()
        await repo.create(
            tenant_id=uuid4(),
            widget_id=uuid4(),
            visitor_session="test-session",
            conversation_id=expected_id,
        )

    assert len(added_models) == 1
    assert added_models[0].id == expected_id


@pytest.mark.asyncio
async def test_create_without_conversation_id_uses_server_default() -> None:
    """create() without a conversation_id leaves id unset (server generates it)."""
    added_models: list = []

    session = MagicMock()
    session.add = MagicMock(side_effect=lambda m: added_models.append(m))
    session.flush = AsyncMock()
    session.refresh = AsyncMock()

    repo = PostgresConversationRepository(session)
    with patch("app.adapters.repositories.conversation_repository._to_entity") as mock_entity:
        mock_entity.return_value = MagicMock()
        await repo.create(
            tenant_id=uuid4(),
            widget_id=uuid4(),
            visitor_session="test-session",
        )

    assert len(added_models) == 1
    # id should not have been explicitly set (server default applies after flush)
    assert added_models[0].__dict__.get("id") is None


@pytest.mark.asyncio
async def test_update_escalation_raises_when_row_not_found() -> None:
    """update_escalation raises LookupError (not AttributeError) if the row
    cannot be fetched after the UPDATE — e.g. session expired or RLS blocked."""
    session = MagicMock()
    session.execute = AsyncMock(return_value=None)
    session.get = AsyncMock(return_value=None)  # simulate missing row

    repo = PostgresConversationRepository(session)
    with pytest.raises(LookupError, match="not found after escalation update"):
        await repo.update_escalation(
            conversation_id=uuid4(),
            tenant_id=uuid4(),
            reason="llm_unavailable",
        )
