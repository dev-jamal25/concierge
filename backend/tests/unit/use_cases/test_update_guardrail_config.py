"""Unit tests for UpdateGuardrailConfigUseCase (T123).

Uses in-memory fakes implementing TenantRepository / AuditRepository protocols.
"""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID, uuid4

import pytest

from app.entities.audit_entry import AuditOutcome
from app.entities.guardrail_config import GuardrailConfig
from app.entities.tenant import Tenant, TenantStatus
from app.use_cases.update_guardrail_config import UpdateGuardrailConfigUseCase


class FakeTenantRepository:
    """In-memory TenantRepository for use-case tests. Implements only the
    methods the use case actually calls; everything else raises if touched."""

    def __init__(self) -> None:
        self.tenants: dict[UUID, Tenant] = {}
        self.update_calls: list[tuple[UUID, dict]] = []

    async def get(self, tenant_id: UUID) -> Tenant | None:
        return self.tenants.get(tenant_id)

    async def update(self, tenant_id: UUID, **changes: object) -> Tenant:
        tenant = self.tenants[tenant_id]
        for key, value in changes.items():
            setattr(tenant, key, value)
        self.update_calls.append((tenant_id, dict(changes)))
        return tenant

    # The protocol surface the use case does not call:
    async def create(self, **_: object) -> Tenant: raise NotImplementedError
    async def get_by_slug(self, _: str) -> Tenant | None: raise NotImplementedError
    async def list(self) -> list[Tenant]: raise NotImplementedError
    async def set_status(self, _: UUID, __: TenantStatus) -> None: raise NotImplementedError
    async def delete(self, _: UUID) -> None: raise NotImplementedError
    async def add_allowed_origin(self, *_: object) -> object: raise NotImplementedError
    async def list_allowed_origins(self, _: UUID) -> list[object]: raise NotImplementedError
    async def create_widget(self, *_: object) -> None: raise NotImplementedError


class FakeAuditRepository:
    def __init__(self) -> None:
        self.entries: list[dict] = []

    async def log(
        self,
        *,
        action: str,
        outcome: AuditOutcome,
        actor_user_id: UUID | None = None,
        target_tenant_id: UUID | None = None,
        details: dict | None = None,
    ) -> None:
        self.entries.append({
            "action": action,
            "outcome": outcome,
            "actor_user_id": actor_user_id,
            "target_tenant_id": target_tenant_id,
            "details": details or {},
        })

    async def list_all(self) -> list[object]: raise NotImplementedError


@pytest.fixture
def tenant_id() -> UUID:
    return uuid4()


@pytest.fixture
def tenants(tenant_id: UUID) -> FakeTenantRepository:
    repo = FakeTenantRepository()
    repo.tenants[tenant_id] = Tenant(id=tenant_id, slug="acme", display_name="Acme")
    return repo


@pytest.fixture
def audit() -> FakeAuditRepository:
    return FakeAuditRepository()


@pytest.fixture
def use_case(tenants: FakeTenantRepository, audit: FakeAuditRepository) -> UpdateGuardrailConfigUseCase:
    return UpdateGuardrailConfigUseCase(tenant_repo=tenants, audit_repo=audit)


def _good_config(tenant_id: UUID, **overrides: object) -> GuardrailConfig:
    base = {
        "tenant_id": tenant_id,
        "updated_at": datetime(2026, 5, 27, 12, 0, tzinfo=timezone.utc),
        "allowed_topics": ["hours", "pricing"],
        "blocked_topics": ["competitor_x"],
        "refusal_tone": "friendly",
        "enabled_tools": ["rag_search", "capture_lead"],
    }
    base.update(overrides)
    return GuardrailConfig(**base)  # type: ignore[arg-type]


async def test_valid_update_succeeds(
    use_case: UpdateGuardrailConfigUseCase,
    tenants: FakeTenantRepository,
    audit: FakeAuditRepository,
    tenant_id: UUID,
) -> None:
    config = _good_config(tenant_id)
    result = await use_case.execute(config, actor_user_id=uuid4())

    # Returned config is the same config we passed in.
    assert result is config

    # Persisted as JSONB on tenants.guardrail_config.
    assert len(tenants.update_calls) == 1
    persisted = tenants.update_calls[0][1]["guardrail_config"]
    assert persisted["allowed_topics"] == ["hours", "pricing"]
    assert persisted["enabled_tools"] == ["capture_lead", "rag_search"]  # sorted on save
    assert persisted["refusal_tone"] == "friendly"
    assert persisted["updated_at"] == "2026-05-27T12:00:00+00:00"

    # Exactly one success audit entry.
    assert len(audit.entries) == 1
    entry = audit.entries[0]
    assert entry["action"] == "guardrail_config_updated"
    assert entry["outcome"] is AuditOutcome.SUCCESS
    assert entry["target_tenant_id"] == tenant_id


async def test_block_platform_rail_raises_permission_error_and_audits(
    use_case: UpdateGuardrailConfigUseCase,
    tenants: FakeTenantRepository,
    audit: FakeAuditRepository,
    tenant_id: UUID,
) -> None:
    config = _good_config(tenant_id, blocked_topics=["prompt_injection_defense", "spam_topic"])

    with pytest.raises(PermissionError, match="cannot weaken platform rails"):
        await use_case.execute(config)

    # Nothing was persisted.
    assert tenants.update_calls == []

    # One denied audit entry with the violating rails listed.
    assert len(audit.entries) == 1
    entry = audit.entries[0]
    assert entry["action"] == "guardrail_weakening_attempt"
    assert entry["outcome"] is AuditOutcome.DENIED
    assert entry["target_tenant_id"] == tenant_id
    assert entry["details"]["blocked_platform_rails"] == ["prompt_injection_defense"]
    assert entry["details"]["enabled_tools_empty"] is False


async def test_empty_enabled_tools_raises_permission_error_and_audits(
    use_case: UpdateGuardrailConfigUseCase,
    tenants: FakeTenantRepository,
    audit: FakeAuditRepository,
    tenant_id: UUID,
) -> None:
    config = _good_config(tenant_id, enabled_tools=[])

    with pytest.raises(PermissionError, match="cannot weaken platform rails"):
        await use_case.execute(config)

    assert tenants.update_calls == []
    assert len(audit.entries) == 1
    entry = audit.entries[0]
    assert entry["action"] == "guardrail_weakening_attempt"
    assert entry["outcome"] is AuditOutcome.DENIED
    assert entry["details"]["enabled_tools_empty"] is True
    assert entry["details"]["blocked_platform_rails"] == []


async def test_invalid_tool_name_raises_value_error_no_audit(
    use_case: UpdateGuardrailConfigUseCase,
    tenants: FakeTenantRepository,
    audit: FakeAuditRepository,
    tenant_id: UUID,
) -> None:
    config = _good_config(tenant_id, enabled_tools=["rag_search", "evil_tool"])

    with pytest.raises(ValueError, match="unknown tool"):
        await use_case.execute(config)

    # Shape errors are programming errors, not policy violations -- no audit,
    # no persistence.
    assert tenants.update_calls == []
    assert audit.entries == []


async def test_unknown_tenant_raises_value_error(
    use_case: UpdateGuardrailConfigUseCase,
    audit: FakeAuditRepository,
) -> None:
    config = _good_config(uuid4())  # tenant_id not in the fake repo

    with pytest.raises(ValueError, match="not found"):
        await use_case.execute(config)

    assert audit.entries == []
