"""Contract conformance for CMS routes (T090).

Asserts /cms/pages endpoints and response shapes match api.openapi.yaml.
No DB needed — only the generated OpenAPI is inspected.
"""

from __future__ import annotations

import pytest

from app.frameworks.api.main import create_app


@pytest.fixture(scope="module")
def openapi() -> dict:
    return create_app().openapi()


def test_cms_pages_list_path(openapi: dict) -> None:
    assert "/cms/pages" in openapi["paths"]
    assert "get" in openapi["paths"]["/cms/pages"]


def test_cms_pages_create_path(openapi: dict) -> None:
    assert "post" in openapi["paths"]["/cms/pages"]


def test_cms_page_detail_paths(openapi: dict) -> None:
    assert "/cms/pages/{page_id}" in openapi["paths"]
    page_path = openapi["paths"]["/cms/pages/{page_id}"]
    assert "get" in page_path
    assert "put" in page_path
    assert "delete" in page_path


def test_cms_publish_path(openapi: dict) -> None:
    assert "/cms/pages/{page_id}/publish" in openapi["paths"]
    assert "post" in openapi["paths"]["/cms/pages/{page_id}/publish"]


def test_cms_unpublish_path(openapi: dict) -> None:
    assert "/cms/pages/{page_id}/unpublish" in openapi["paths"]
    assert "post" in openapi["paths"]["/cms/pages/{page_id}/unpublish"]


def test_cms_page_out_schema_fields(openapi: dict) -> None:
    # FastAPI emits $ref → resolve via components/schemas
    schema = openapi["components"]["schemas"]["CMSPageOut"]
    props = schema.get("properties", {})
    for field in ["id", "tenant_id", "title", "body", "state", "slug", "created_at", "updated_at"]:
        assert field in props, f"Missing field '{field}' in CMSPageOut schema"


def test_cms_create_request_required_fields(openapi: dict) -> None:
    # FastAPI emits $ref → resolve via components/schemas
    schema = openapi["components"]["schemas"]["CMSPageCreate"]
    assert set(schema.get("required", [])) >= {"title", "body", "slug"}


def test_cms_create_returns_201(openapi: dict) -> None:
    post = openapi["paths"]["/cms/pages"]["post"]
    assert "201" in post["responses"]


def test_cms_delete_returns_204(openapi: dict) -> None:
    delete = openapi["paths"]["/cms/pages/{page_id}"]["delete"]
    assert "204" in delete["responses"]


def test_cms_publish_returns_202(openapi: dict) -> None:
    post = openapi["paths"]["/cms/pages/{page_id}/publish"]["post"]
    assert "202" in post["responses"]
