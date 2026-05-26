"""UserRepository protocol (T020) — Layer 2 interface."""

from __future__ import annotations

from typing import Protocol
from uuid import UUID

from app.entities.user import User, UserRole


class UserRepository(Protocol):
    async def create(self, *, email: str, hashed_password: str, role: UserRole) -> User: ...

    async def get(self, user_id: UUID) -> User | None: ...

    async def get_by_email(self, email: str) -> User | None: ...

    async def update(self, user_id: UUID, **changes: object) -> User: ...

    async def bind_tenant_role(self, user_id: UUID, tenant_id: UUID) -> None:
        """Create a user_tenant_roles row mapping a tenant_admin to a tenant."""
        ...
