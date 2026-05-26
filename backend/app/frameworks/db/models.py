"""SQLAlchemy ORM models (T016) — Layer 4. Mirrors the entities and the schema
in data-model.md. NEVER imported from entities/ or use_cases/.

Owner A owns: tenants, users, user_tenant_roles, invitations, allowed_origins,
audit_entries. (allowed_origins is created in migration 003 but modelled here.)
Other tenant-scoped tables (cms_pages, chunks, conversations, messages, leads,
widgets) are owned by other slices and defined in their migrations/models.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.frameworks.db.base import Base

_UUID_PK = text("gen_random_uuid()")
_NOW = text("now()")


class TenantModel(Base):
    __tablename__ = "tenants"

    id: Mapped[str] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=_UUID_PK)
    slug: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    display_name: Mapped[str] = mapped_column(Text, nullable=False)
    plan: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'poc'"))
    persona_config: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    theme_config: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    guardrail_config: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'active'"))
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False, server_default=_NOW)
    updated_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False, server_default=_NOW)


class UserModel(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=_UUID_PK)
    email: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    hashed_password: Mapped[str] = mapped_column(Text, nullable=False)
    # Aligned with migration 001 (created there, not deferred to 003).
    role: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("true"))
    is_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False, server_default=_NOW)


class UserTenantRoleModel(Base):
    __tablename__ = "user_tenant_roles"

    user_id: Mapped[str] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    tenant_id: Mapped[str] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), primary_key=True
    )
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False, server_default=_NOW)


class InvitationModel(Base):
    __tablename__ = "invitations"

    id: Mapped[str] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=_UUID_PK)
    tenant_id: Mapped[str] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    email: Mapped[str] = mapped_column(Text, nullable=False)
    token_hash: Mapped[str] = mapped_column(Text, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False)
    accepted_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    created_by: Mapped[str] = mapped_column(UUID(as_uuid=True), ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False, server_default=_NOW)

    __table_args__ = (
        # Partial unique: one pending (un-accepted) invite per (tenant, email).
        Index(
            "uq_invitations_pending",
            "tenant_id",
            "email",
            unique=True,
            postgresql_where=text("accepted_at IS NULL"),
        ),
    )


class AllowedOriginModel(Base):
    __tablename__ = "allowed_origins"

    id: Mapped[str] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=_UUID_PK)
    tenant_id: Mapped[str] = mapped_column(
        UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False
    )
    origin: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False, server_default=_NOW)

    __table_args__ = (UniqueConstraint("tenant_id", "origin", name="uq_allowed_origin"),)


class AuditEntryModel(Base):
    __tablename__ = "audit_entries"

    id: Mapped[str] = mapped_column(UUID(as_uuid=True), primary_key=True, server_default=_UUID_PK)
    actor_user_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=True), ForeignKey("users.id"), nullable=True
    )
    # NOT a foreign key — must survive the tenant it referenced (append-only log).
    target_tenant_id: Mapped[str | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    action: Mapped[str] = mapped_column(String(64), nullable=False)
    outcome: Mapped[str] = mapped_column(String(32), nullable=False)
    details: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    created_at: Mapped[datetime] = mapped_column(TIMESTAMP(timezone=True), nullable=False, server_default=_NOW)

    __table_args__ = (
        Index("ix_audit_target_tenant", "target_tenant_id", "created_at"),
        Index("ix_audit_actor", "actor_user_id", "created_at"),
    )
