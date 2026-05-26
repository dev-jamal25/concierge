"""Hashicorp Vault client (T038) — Layer 4 adapter implementing VaultClient.

KV v2 wrapper over hvac. hvac is synchronous, so blocking calls are offloaded to
a thread to satisfy the async protocol. At startup, `ensure_widget_signing_key`
generates (or retrieves) an Ed25519 signing key at `secret/jwt/widget/active`;
the widget TokenSigner (Owner D) consumes it. The same Vault also issues the
service credential shared with the modelserver / guardrails sidecars (Owner C).
"""

from __future__ import annotations

import asyncio

import hvac
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from app.frameworks.config import Settings, get_settings

WIDGET_SIGNING_KEY_PATH = "jwt/widget/active"


class HvacVaultClient:
    """Implements the use_cases.protocols.vault_client.VaultClient protocol."""

    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or get_settings()
        self._client = hvac.Client(
            url=self._settings.vault_addr, token=self._settings.vault_token
        )
        self._mount = self._settings.vault_kv_mount

    async def get_secret(self, path: str) -> dict[str, str] | None:
        def _read() -> dict[str, str] | None:
            try:
                resp = self._client.secrets.kv.v2.read_secret_version(
                    path=path, mount_point=self._mount, raise_on_deleted_version=False
                )
            except hvac.exceptions.InvalidPath:
                return None
            return resp["data"]["data"]

        return await asyncio.to_thread(_read)

    async def set_secret(self, path: str, value: dict[str, str]) -> None:
        def _write() -> None:
            self._client.secrets.kv.v2.create_or_update_secret(
                path=path, secret=value, mount_point=self._mount
            )

        await asyncio.to_thread(_write)

    async def rotate_key(self, key_id: str) -> str:
        """Generate a fresh Ed25519 key and store it; returns the storage path."""
        private_pem = _generate_ed25519_pem()
        await self.set_secret(key_id, {"private_key_pem": private_pem})
        return key_id

    async def ensure_widget_signing_key(self) -> str:
        """Idempotently provision the widget JWT signing key. Returns the PEM."""
        existing = await self.get_secret(WIDGET_SIGNING_KEY_PATH)
        if existing and "private_key_pem" in existing:
            return existing["private_key_pem"]
        pem = _generate_ed25519_pem()
        await self.set_secret(WIDGET_SIGNING_KEY_PATH, {"private_key_pem": pem})
        return pem


def _generate_ed25519_pem() -> str:
    key = Ed25519PrivateKey.generate()
    pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    return pem.decode("utf-8")
