"""Contract checks for Owner D widget endpoints."""

from __future__ import annotations

import pytest

from app.frameworks.api.main import create_app


@pytest.fixture(scope="module")
def openapi() -> dict:
    return create_app().openapi()


def _props(openapi: dict, schema_name: str) -> set[str]:
    return set(openapi["components"]["schemas"][schema_name]["properties"].keys())


def test_widget_paths_present(openapi: dict) -> None:
    paths = openapi["paths"]
    assert "post" in paths["/widget/token"]
    assert "get" in paths["/widget/config"]


def test_widget_token_request_shape(openapi: dict) -> None:
    assert {"widget_id", "origin"} <= _props(openapi, "WidgetTokenRequest")


def test_widget_token_response_shape(openapi: dict) -> None:
    assert {"token", "expires_in_seconds"} <= _props(openapi, "WidgetTokenResponse")


def test_widget_config_response_shape(openapi: dict) -> None:
    assert {
        "theme_config",
        "greeting",
        "persona_summary",
        "consent_notice",
    } <= _props(openapi, "WidgetConfigResponse")
