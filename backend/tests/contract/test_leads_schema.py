"""Contract conformance for leads routes (T120).

Asserts /leads and /leads/export endpoints match api.openapi.yaml.
No DB needed — only the generated OpenAPI is inspected.
"""

from __future__ import annotations

import pytest

from app.frameworks.api.main import create_app


@pytest.fixture(scope="module")
def openapi() -> dict:
    return create_app().openapi()


def test_leads_list_path(openapi: dict) -> None:
    assert "/leads" in openapi["paths"]
    assert "get" in openapi["paths"]["/leads"]


def test_leads_export_path(openapi: dict) -> None:
    assert "/leads/export" in openapi["paths"]
    assert "get" in openapi["paths"]["/leads/export"]


def test_leads_list_since_param(openapi: dict) -> None:
    get = openapi["paths"]["/leads"]["get"]
    params = {p["name"]: p for p in get.get("parameters", [])}
    assert "since" in params
    assert params["since"]["in"] == "query"


def test_leads_list_response_200(openapi: dict) -> None:
    get = openapi["paths"]["/leads"]["get"]
    assert "200" in get["responses"]


def test_leads_export_response_200(openapi: dict) -> None:
    get = openapi["paths"]["/leads/export"]["get"]
    assert "200" in get["responses"]


def test_leads_list_response_fields(openapi: dict) -> None:
    # FastAPI emits $ref in items → resolve via components/schemas
    schema = openapi["components"]["schemas"]["LeadOut"]
    props = schema.get("properties", {})
    for field in ["id", "tenant_id", "conversation_id", "contact", "intent", "created_at"]:
        assert field in props, f"Missing field '{field}' in LeadOut schema"
