"""UpdateGuardrailConfigUseCase (T123) — Layer 2.

Validates and persists a tenant's updated `GuardrailConfig`. Enforces the
NON-NEGOTIABLE rule from constitution Principle V: a tenant cannot weaken
platform rails. Any attempt to weaken (blocked-topics naming a platform rail,
or `enabled_tools` empty so the agent has no actionable surface) raises
`PermissionError` and writes an audit entry with `outcome=DENIED`.

Depends on `TenantRepository` and `AuditRepository` *protocols* only -- the
concrete adapters are injected at the composition root (T036). Never imports a
concrete adapter (Clean Architecture, Principle I).
"""

from __future__ import annotations

from typing import Final
from uuid import UUID

from app.entities.audit_entry import AuditOutcome
from app.entities.guardrail_config import GuardrailConfig
from app.use_cases.protocols.audit_repository import AuditRepository
from app.use_cases.protocols.tenant_repository import TenantRepository

# Platform rails are locked at the platform level and mirrored in the
# guardrails sidecar (services/guardrails/rails/platform/). A tenant config
# that *names* any of these in blocked_topics is interpreted as an attempt to
# disable them and is denied + audited.
PLATFORM_RAILS: Final[frozenset[str]] = frozenset(
    {
        "prompt_injection_defense",
        "jailbreak_defense",
        "cross_tenant_refusal",
        "pii_redaction",
    }
)


class UpdateGuardrailConfigUseCase:
    """Persist a tenant's guardrail config, refusing any platform-rail weakening."""

    def __init__(
        self,
        *,
        tenant_repo: TenantRepository,
        audit_repo: AuditRepository,
    ) -> None:
        self._tenants = tenant_repo
        self._audit = audit_repo

    async def execute(
        self,
        config: GuardrailConfig,
        *,
        actor_user_id: UUID | None = None,
    ) -> GuardrailConfig:
        tenant = await self._tenants.get(config.tenant_id)
        if tenant is None:
            raise ValueError(f"tenant {config.tenant_id} not found")

        # (a) Shape validation -- unknown tool names are a programming error,
        # not a policy violation, so they raise ValueError and are NOT audited.
        config.validate()

        # (b) Policy: platform rails must not be weakened.
        blocked_platform_rails = sorted(set(config.blocked_topics) & PLATFORM_RAILS)
        enabled_tools_empty = len(config.enabled_tools) == 0
        if blocked_platform_rails or enabled_tools_empty:
            await self._audit.log(
                action="guardrail_weakening_attempt",
                outcome=AuditOutcome.DENIED,
                actor_user_id=actor_user_id,
                target_tenant_id=config.tenant_id,
                details={
                    "blocked_platform_rails": blocked_platform_rails,
                    "enabled_tools_empty": enabled_tools_empty,
                    "refusal_tone": config.refusal_tone,
                },
            )
            raise PermissionError("tenant cannot weaken platform rails")

        # (c) Persist as JSONB on tenants.guardrail_config.
        await self._tenants.update(
            config.tenant_id,
            guardrail_config=_to_jsonb(config),
        )

        # (d) Success audit.
        await self._audit.log(
            action="guardrail_config_updated",
            outcome=AuditOutcome.SUCCESS,
            actor_user_id=actor_user_id,
            target_tenant_id=config.tenant_id,
            details={
                "allowed_topics_count": len(config.allowed_topics),
                "blocked_topics_count": len(config.blocked_topics),
                "enabled_tools": sorted(config.enabled_tools),
                "refusal_tone": config.refusal_tone,
            },
        )
        return config


def _to_jsonb(config: GuardrailConfig) -> dict:
    """Serialize the policy-bearing fields for the tenants.guardrail_config column.

    tenant_id is the row key, not part of the JSONB payload.
    """
    return {
        "allowed_topics": list(config.allowed_topics),
        "blocked_topics": list(config.blocked_topics),
        "refusal_tone": config.refusal_tone,
        "enabled_tools": sorted(config.enabled_tools),
        "updated_at": config.updated_at.isoformat(),
    }
