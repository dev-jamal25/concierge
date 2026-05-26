"""ModelserverClassifier (T047) — Layer 3 adapter implementing ClassifierClient.

Stub HTTP client to the lean classifier serving container. Mirrors the wire
contract in `specs/001-concierge-platform/contracts/internal/modelserver.yaml`
(`POST /predict`). The Vault-issued `X-Service-Token` is wired in T151.
"""

from __future__ import annotations

from typing import cast
from uuid import UUID

import httpx

from app.use_cases.protocols.classifier_client import ClassifierLabel, ClassifierResult


class ModelserverClassifier:
    """Implements use_cases.protocols.classifier_client.ClassifierClient."""

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

    async def classify(self, *, message: str, tenant_id: UUID) -> ClassifierResult:
        response = await self._client.post(
            f"{self._base_url}/predict",
            json={"message": message, "tenant_id": str(tenant_id)},
            headers={"X-Service-Token": self._service_token},
        )
        response.raise_for_status()
        payload = response.json()
        return ClassifierResult(
            label=cast(ClassifierLabel, payload["label"]),
            confidence=float(payload["confidence"]),
            per_class={k: float(v) for k, v in payload["per_class"].items()},
            artifact_sha256=payload.get("artifact_sha256", ""),
        )
