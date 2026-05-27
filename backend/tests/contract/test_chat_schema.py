"""Contract conformance for the chat + CMS surface (T081).

Asserts the FastAPI app exposes the paths and response shapes defined in
specs/001-concierge-platform/contracts/api.openapi.yaml for Slice B.
No DB needed — only the generated OpenAPI is inspected.
"""

from __future__ import annotations

import pytest

from app.frameworks.api.main import create_app


@pytest.fixture(scope="module")
def openapi() -> dict:
    return create_app().openapi()


def _props(openapi: dict, name: str) -> set[str]:
    return set(openapi["components"]["schemas"][name]["properties"].keys())


# --- /chat ---


def test_chat_path_present(openapi: dict) -> None:
    assert "post" in openapi["paths"]["/chat"]


def test_chat_request_body(openapi: dict) -> None:
    post = openapi["paths"]["/chat"]["post"]
    schema = post["requestBody"]["content"]["application/json"]["schema"]
    assert "conversation_id" in schema["properties"]
    assert "message" in schema["properties"]
    assert set(schema.get("required", [])) >= {"conversation_id", "message"}


def test_chat_response_200(openapi: dict) -> None:
    post = openapi["paths"]["/chat"]["post"]
    assert "200" in post["responses"]


def test_chat_response_503(openapi: dict) -> None:
    post = openapi["paths"]["/chat"]["post"]
    assert "503" in post["responses"]


def test_chat_turn_response_shape(openapi: dict) -> None:
    props = _props(openapi, "ChatTurnResponse")
    assert {"route", "reply", "escalated", "retrieved_chunks", "capture_lead_status"} <= props


def test_chat_turn_route_enum(openapi: dict) -> None:
    schema = openapi["components"]["schemas"]["ChatTurnResponse"]
    route_enum = schema["properties"]["route"].get("enum", [])
    assert set(route_enum) >= {"spam", "faq", "lead_intent", "escalate", "agent", "unavailable"}
