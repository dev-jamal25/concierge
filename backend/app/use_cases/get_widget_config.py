"""Return visitor-safe widget config."""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from app.use_cases.protocols.tenant_repository import TenantRepository


class WidgetConfigNotFoundError(Exception):
    pass


@dataclass(frozen=True, slots=True)
class WidgetConfig:
    theme_config: dict
    greeting: str
    persona_summary: str
    consent_notice: str


class GetWidgetConfigUseCase:
    def __init__(self, tenants: TenantRepository) -> None:
        self._tenants = tenants

    async def execute(self, tenant_id: UUID) -> WidgetConfig:
        tenant = await self._tenants.get(tenant_id)
        if tenant is None:
            raise WidgetConfigNotFoundError(str(tenant_id))

        theme = tenant.theme_config or {}
        persona = tenant.persona_config or {}
        return WidgetConfig(
            theme_config=theme,
            greeting=str(theme.get("greeting", "Hi, how can I help?")),
            persona_summary=str(persona.get("summary", "")),
            consent_notice=str(
                theme.get(
                    "consent_notice",
                    "By chatting, you agree to share this conversation with the site owner.",
                )
            ),
        )
