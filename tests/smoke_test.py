"""HTTP smoke test for the running Concierge compose stack."""

from __future__ import annotations

import os
from uuid import uuid4

import httpx

API_BASE_URL = os.getenv("SMOKE_API_BASE_URL", "http://localhost:8000")
WIDGET_ID = os.getenv("SMOKE_WIDGET_ID", "lumiere-widget-v1")
ALLOWED_ORIGIN = os.getenv("SMOKE_ORIGIN", "http://localhost:3001")


def test_public_widget_chat_path() -> None:
    with httpx.Client(base_url=API_BASE_URL, timeout=10.0) as client:
        health = client.get("/healthz")
        assert health.status_code == 200, health.text
        assert health.json() == {"status": "ok"}

        token_response = client.post(
            "/widget/token",
            json={"widget_id": WIDGET_ID, "origin": ALLOWED_ORIGIN},
        )
        assert token_response.status_code == 200, token_response.text
        token_body = token_response.json()
        assert isinstance(token_body.get("token"), str)
        assert token_body["expires_in_seconds"] > 0

        chat_response = client.post(
            "/chat",
            headers={
                "Authorization": f"Bearer {token_body['token']}",
                "Origin": ALLOWED_ORIGIN,
            },
            json={
                "conversation_id": str(uuid4()),
                "message": "book a table for 4 tonight",
            },
        )
        assert chat_response.status_code == 200, chat_response.text
        chat_body = chat_response.json()
        assert chat_body["route"] == "lead_intent"
        assert chat_body["reply"]
        assert chat_body["escalated"] is False
        assert isinstance(chat_body["retrieved_chunks"], list)
        assert chat_body["capture_lead_status"] == "not_captured"
