"""Shared fixtures for the red-team / PII-canary eval gates (T142, T143)."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[3]
SIDECAR_APP = PROJECT_ROOT / "services" / "guardrails" / "app.py"


@pytest.fixture(scope="session")
def sidecar():
    """Import services/guardrails/app.py under a unique name.

    The sidecar module is literally named `app`, which collides with the backend
    `app` package on sys.path, so we load it by file path. Registering it in
    sys.modules before exec lets @dataclass resolve cls.__module__ during load."""
    spec = importlib.util.spec_from_file_location("guardrails_sidecar_app", SIDECAR_APP)
    assert spec and spec.loader, f"cannot load sidecar module from {SIDECAR_APP}"
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="session")
def platform_rails(sidecar):
    return sidecar.load_platform_rails()
