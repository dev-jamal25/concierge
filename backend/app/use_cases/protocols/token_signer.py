"""Token signer protocol owned by Slice D."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import timedelta
from typing import Any, Protocol


class TokenSigner(Protocol):
    def sign_token(self, claims: Mapping[str, Any], ttl: timedelta) -> str: ...

    def verify_token(self, token: str) -> dict[str, Any]: ...
