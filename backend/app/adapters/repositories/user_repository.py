"""PostgresUserRepository (T112) — implements UserRepository.

Password hashing reuses fastapi-users' PasswordHelper (Argon2id by default), per
plan.md. Creating a user_tenant_roles row binds a tenant_admin to a tenant.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import insert, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.entities.user import User, UserRole
from app.frameworks.db.models import UserModel, UserTenantRoleModel


def _to_user(row: UserModel) -> User:
    return User(
        id=row.id,
        email=row.email,
        hashed_password=row.hashed_password,
        role=UserRole(row.role),
        is_active=row.is_active,
        is_verified=row.is_verified,
        created_at=row.created_at,
    )


class PostgresUserRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def create(self, *, email: str, hashed_password: str, role: UserRole) -> User:
        row = UserModel(email=email, hashed_password=hashed_password, role=role.value)
        self._s.add(row)
        await self._s.flush()
        await self._s.refresh(row)
        return _to_user(row)

    async def get(self, user_id: UUID) -> User | None:
        row = await self._s.get(UserModel, user_id)
        return _to_user(row) if row else None

    async def get_by_email(self, email: str) -> User | None:
        row = (
            await self._s.execute(select(UserModel).where(UserModel.email == email))
        ).scalar_one_or_none()
        return _to_user(row) if row else None

    async def update(self, user_id: UUID, **changes: object) -> User:
        await self._s.execute(
            update(UserModel).where(UserModel.id == user_id).values(**changes)
        )
        row = await self._s.get(UserModel, user_id)
        assert row is not None
        return _to_user(row)

    async def bind_tenant_role(self, user_id: UUID, tenant_id: UUID) -> None:
        await self._s.execute(
            insert(UserTenantRoleModel).values(user_id=user_id, tenant_id=tenant_id)
        )

    async def primary_tenant_id(self, user_id: UUID) -> UUID | None:
        """The (first) tenant a tenant_admin is bound to. tenant_manager has none."""
        return (
            await self._s.execute(
                select(UserTenantRoleModel.tenant_id)
                .where(UserTenantRoleModel.user_id == user_id)
                .limit(1)
            )
        ).scalar_one_or_none()
