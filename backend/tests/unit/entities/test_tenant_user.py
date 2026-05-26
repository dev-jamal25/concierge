"""Unit tests for the Tenant and User entities (Phase 1 TDD)."""

from __future__ import annotations

from uuid import uuid4

from app.entities.tenant import Tenant, TenantPlan, TenantStatus
from app.entities.user import User, UserRole


def test_tenant_defaults() -> None:
    t = Tenant(id=uuid4(), slug="acme-co", display_name="ACME Inc.")
    assert t.plan is TenantPlan.POC
    assert t.status is TenantStatus.ACTIVE
    assert t.persona_config == {}
    assert t.theme_config == {}
    assert t.guardrail_config == {}


def test_tenant_config_dicts_are_independent() -> None:
    a = Tenant(id=uuid4(), slug="a", display_name="A")
    b = Tenant(id=uuid4(), slug="b", display_name="B")
    a.persona_config["voice"] = "warm"
    assert b.persona_config == {}


def test_tenant_status_lifecycle_values() -> None:
    assert {s.value for s in TenantStatus} == {"active", "erasing", "erased"}


def test_user_role_enum_values() -> None:
    assert UserRole.TENANT_MANAGER.value == "tenant_manager"
    assert UserRole.TENANT_ADMIN.value == "tenant_admin"


def test_user_defaults() -> None:
    u = User(
        id=uuid4(),
        email="admin@acme.example.com",
        hashed_password="x",
        role=UserRole.TENANT_ADMIN,
    )
    assert u.is_active is True
    assert u.is_verified is False
