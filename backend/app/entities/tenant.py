"""Tenant entity (T014) — Layer 1. Pure dataclass, no I/O, no framework imports."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from uuid import UUID


class TenantPlan(StrEnum):
    POC = "poc"
    GROWTH = "growth"
    PRODUCTION = "production"


class TenantStatus(StrEnum):
    ACTIVE = "active"
    ERASING = "erasing"
    ERASED = "erased"


@dataclass(slots=True)
class Tenant:
    id: UUID
    slug: str
    display_name: str
    plan: TenantPlan = TenantPlan.POC
    status: TenantStatus = TenantStatus.ACTIVE
    persona_config: dict = field(default_factory=dict)
    theme_config: dict = field(default_factory=dict)
    guardrail_config: dict = field(default_factory=dict)
    created_at: datetime | None = None
    updated_at: datetime | None = None
