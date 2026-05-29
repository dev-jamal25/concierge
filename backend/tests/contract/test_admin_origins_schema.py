"""Contract checks for Owner D admin origins endpoints."""

from __future__ import annotations

import pytest

from app.frameworks.api.main import create_app


@pytest.fixture(scope="module")
def openapi() -> dict:
    return create_app().openapi()


def _props(openapi: dict, schema_name: str) -> set[str]:
    return set(openapi["components"]["schemas"][schema_name]["properties"].keys())


def test_admin_origins_paths_present(openapi: dict) -> None:
    """Verify admin origins endpoints are in the OpenAPI spec."""
    paths = openapi["paths"]
    assert "/admin/origins" in paths
    assert "get" in paths["/admin/origins"]
    assert "post" in paths["/admin/origins"]
    assert "/admin/origins/{origin_id}" in paths
    assert "delete" in paths["/admin/origins/{origin_id}"]


def test_allowed_origin_out_shape(openapi: dict) -> None:
    """Verify AllowedOriginOut schema has required properties."""
    props = _props(openapi, "AllowedOriginOut")
    assert {"id", "tenant_id", "origin"} <= props


def test_allowed_origin_create_shape(openapi: dict) -> None:
    """Verify AllowedOriginCreate schema has required properties."""
    props = _props(openapi, "AllowedOriginCreate")
    assert {"origin"} <= props


def test_admin_widget_path_present(openapi: dict) -> None:
    """Verify /admin/widget endpoint is in the OpenAPI spec."""
    paths = openapi["paths"]
    assert "/admin/widget" in paths
    assert "get" in paths["/admin/widget"]


def test_widget_info_out_shape(openapi: dict) -> None:
    """Verify WidgetInfoOut schema has required properties."""
    props = _props(openapi, "WidgetInfoOut")
    assert {"widget_id", "is_enabled"} <= props
