"""NeMoGuardrails (T048) — Layer 3 adapter implementing GuardrailsClient.

Stub HTTP client to the NeMo Guardrails sidecar. Mirrors the wire contract in
`specs/001-concierge-platform/contracts/internal/guardrails.yaml` (`POST /check`).
Platform + tenant rails are enforced inside the sidecar (T172); this adapter
only ferries the request and parses the decision.
"""

from __future__ import annotations

from typing import cast
from uuid import UUID

import httpx

from app.use_cases.protocols.guardrails_client import (
    GuardrailAction,
    GuardrailDecision,
    GuardrailLayer,
    GuardrailRole,
)


class NeMoGuardrails:
    """Implements use_cases.protocols.guardrails_client.GuardrailsClient."""

    def __init__(
        self,
        *,
        base_url: str,
        service_token: str,
        client: httpx.AsyncClient | None = None,
        timeout: float = 5.0,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._service_token = service_token
        self._client = client or httpx.AsyncClient(timeout=timeout)

    async def check(
        self,
        *,
        tenant_id: UUID,
        role: GuardrailRole,
        content: str,
    ) -> GuardrailDecision:
        response = await self._client.post(
            f"{self._base_url}/check",
            json={"tenant_id": str(tenant_id), "role": role, "content": content},
            headers={"X-Service-Token": self._service_token},
        )
        response.raise_for_status()
        payload = response.json()
        rail_layer = payload.get("rail_layer")
        return GuardrailDecision(
            action=cast(GuardrailAction, payload["action"]),
            content=payload["content"],
            triggered_rails=list(payload.get("triggered_rails", [])),
            rail_layer=cast(GuardrailLayer, rail_layer) if rail_layer else None,
        )
