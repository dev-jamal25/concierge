"""PyJWT EdDSA signer for widget JWTs."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timedelta, timezone
from typing import Any

import jwt
from cryptography.hazmat.primitives import serialization


class PyJWTSigner:
    def __init__(
        self,
        private_key_pem: str,
        *,
        key_id: str = "jwt/widget/active",
        issuer: str = "concierge",
        audience: str = "widget",
    ) -> None:
        self._private_key = serialization.load_pem_private_key(
            private_key_pem.encode("utf-8"), password=None
        )
        self._public_key = self._private_key.public_key()
        self._key_id = key_id
        self._issuer = issuer
        self._audience = audience

    def sign_token(self, claims: Mapping[str, Any], ttl: timedelta) -> str:
        now = datetime.now(timezone.utc)
        payload = {
            **dict(claims),
            "iss": self._issuer,
            "aud": self._audience,
            "iat": now,
            "exp": now + min(ttl, timedelta(minutes=5)),
            "kid": self._key_id,
        }
        return jwt.encode(
            payload,
            self._private_key,
            algorithm="EdDSA",
            headers={"kid": self._key_id},
        )

    def verify_token(self, token: str) -> dict[str, Any]:
        return jwt.decode(
            token,
            self._public_key,
            algorithms=["EdDSA"],
            audience=self._audience,
            issuer=self._issuer,
        )
