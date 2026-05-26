"""User entity (T015) — Layer 1. Pure dataclass, no I/O, no framework imports."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID


class UserRole(StrEnum):
    TENANT_MANAGER = "tenant_manager"
    TENANT_ADMIN = "tenant_admin"


@dataclass(slots=True)
class User:
    id: UUID
    email: str
    hashed_password: str
    role: UserRole
    is_active: bool = True
    is_verified: bool = False
    created_at: datetime | None = None
