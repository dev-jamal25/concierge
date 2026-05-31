"""Contract checks for GET /auth/me (T113 extension)."""

from __future__ import annotations

import pytest

from app.frameworks.api.main import create_app


@pytest.fixture(scope="module")
def openapi() -> dict:
    return create_app().openapi()


def _props(openapi: dict, schema_name: str) -> set[str]:
    return set(openapi["components"]["schemas"][schema_name]["properties"].keys())


def test_auth_me_path_present(openapi: dict) -> None:
    paths = openapi["paths"]
    assert "get" in paths["/auth/me"]


def test_auth_me_response_shape(openapi: dict) -> None:
    assert {"user_id", "email", "role", "tenant_id"} <= _props(openapi, "MeResponse")
