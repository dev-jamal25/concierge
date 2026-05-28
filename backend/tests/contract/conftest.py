"""Contract test fixtures.

Sets SERVICE_TOKEN env var before any module-level import of create_app()
so _resolve_service_token() skips the Vault call (dev-mode override path).
Also clears the lru_cache on _resolve_service_token so tests start clean.
"""

from __future__ import annotations

import os

import pytest


def pytest_configure(config: pytest.Config) -> None:
    os.environ.setdefault("SERVICE_TOKEN", "test-token-contract")
