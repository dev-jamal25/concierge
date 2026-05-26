"""Contract conformance for the manager + auth surface (T117).

Asserts the FastAPI app exposes the paths and response shapes defined in
specs/001-concierge-platform/contracts/api.openapi.yaml for Slice A. No DB needed
(only the generated OpenAPI is inspected).
"""

from __future__ import annotations

import pytest

from app.frameworks.api.main import create_app


@pytest.fixture(scope="module")
def openapi() -> dict:
    return create_app().openapi()


def _props(schema: dict, name: str) -> set[str]:
    return set(schema["components"]["schemas"][name]["properties"].keys())


def test_manager_paths_present(openapi: dict) -> None:
    paths = openapi["paths"]
    assert {"get", "post"} <= set(paths["/manager/tenants"])
    assert "delete" in paths["/manager/tenants/{tenant_id}"]
    assert "get" in paths["/manager/audit"]
    assert "get" in paths["/manager/usage"]


def test_auth_paths_present(openapi: dict) -> None:
    paths = openapi["paths"]
    assert "post" in paths["/auth/login"]
    assert "post" in paths["/auth/invitations/{token}/accept"]


def test_tenant_summary_shape(openapi: dict) -> None:
    # Contract TenantSummary fields.
    expected = {"id", "display_name", "slug", "plan", "status", "created_at"}
    assert expected <= _props(openapi, "TenantSummary")


def test_usage_aggregate_shape(openapi: dict) -> None:
    expected = {
        "tenant_count",
        "active_tenant_count",
        "total_conversations_30d",
        "total_leads_30d",
        "total_llm_input_tokens_30d",
        "total_llm_output_tokens_30d",
        "total_embedding_tokens_30d",
    }
    assert expected <= _props(openapi, "UsageAggregate")


def test_audit_entry_shape(openapi: dict) -> None:
    expected = {
        "id",
        "actor_user_id",
        "target_tenant_id",
        "action",
        "outcome",
        "details",
        "created_at",
    }
    assert expected <= _props(openapi, "AuditEntryOut")


def test_provision_request_requires_admin_email(openapi: dict) -> None:
    props = _props(openapi, "ProvisionTenantRequest")
    assert {"display_name", "slug", "first_admin_email"} <= props
