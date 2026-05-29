"""Composition root (T036) — the single place concrete adapters are wired into
use-case protocols. No use case imports a concrete adapter; they receive
implementations from here.

Also hosts the request-scoped tenant dependencies:
- get_current_tenant_id: the token-derived tenant (401 if absent)
- require_matching_tenant: route/dependency-level body-spoof guard (T149)

The body-spoof check lives here, NOT in TenantContextMiddleware (correction #4):
middleware derives context only from the verified token; routes that accept a
tenant_id in their body/path use this guard to reject a mismatch.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass
from functools import lru_cache
from uuid import UUID

import jwt
from fastapi import Depends, Header, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from minio import Minio
from sqlalchemy.ext.asyncio import AsyncSession

from app.adapters.email.console_email import ConsoleEmailSender
from app.adapters.guardrails.nemo_client import NeMoGuardrails
from app.adapters.repositories.audit_repository import PostgresAuditRepository
from app.adapters.repositories.invitation_repository import PostgresInvitationRepository
from app.adapters.repositories.tenant_repository import PostgresTenantRepository
from app.adapters.repositories.user_repository import PostgresUserRepository
from app.adapters.session.redis_session import make_redis_session
from app.adapters.storage.minio_object_storage import MinIOObjectStorage
from app.adapters.tokens.pyjwt_signer import PyJWTSigner
from app.frameworks.config import Settings, get_settings
from app.frameworks.db.session import (
    get_manager_session,
    get_session,
    reset_tenant_id,
    set_tenant_id,
    tenant_id_ctx,
)
from app.frameworks.secrets.vault_client import HvacVaultClient, WIDGET_SIGNING_KEY_PATH
from app.use_cases.erase_tenant import EraseTenantUseCase
from app.use_cases.invite_admin import InviteAdminUseCase
from app.use_cases.protocols.session_store import SessionStore
from app.use_cases.provision_tenant import ProvisionTenantUseCase

# --- Settings ---


def get_app_settings() -> Settings:
    return get_settings()


def get_vault_client() -> HvacVaultClient:
    return HvacVaultClient(get_settings())


def get_llm_client() -> object:
    raise NotImplementedError("LLM client provider is owned by Owner B tasks T025/T044")


def get_embedding_client() -> object:
    raise NotImplementedError("embedding client provider is owned by Owner B tasks T026/T045")


def get_session_store() -> SessionStore:
    return make_redis_session(get_settings().redis_url)


def get_classifier_client() -> object:
    raise NotImplementedError("classifier client provider is owned by Owner C tasks T027/T047")


@lru_cache(maxsize=1)
def _resolve_service_token() -> str:
    """Resolve the shared sidecar X-Service-Token (T151).

    Source of truth is Vault at SERVICE_TOKEN_PATH. The env var SERVICE_TOKEN
    is a dev-only override (tests, no-Vault local runs).
    """
    settings = get_settings()
    if settings.service_token:
        return settings.service_token
    return HvacVaultClient(settings).ensure_service_token_sync()


def get_service_token() -> str:
    """Return the shared X-Service-Token (Vault-first, env fallback)."""
    return _resolve_service_token()


def get_guardrails_client() -> NeMoGuardrails:
    settings = get_settings()
    return NeMoGuardrails(
        base_url=settings.guardrails_url,
        service_token=_resolve_service_token(),
    )


async def get_token_signer() -> PyJWTSigner:
    pem = await get_vault_client().ensure_widget_signing_key()
    return PyJWTSigner(pem, key_id=WIDGET_SIGNING_KEY_PATH)


def get_object_storage() -> MinIOObjectStorage:
    settings = get_settings()
    client = Minio(
        settings.minio_endpoint,
        access_key=settings.minio_access_key,
        secret_key=settings.minio_secret_key,
        secure=settings.minio_secure,
    )
    return MinIOObjectStorage(client=client, bucket_name=settings.minio_bucket)


# --- DB sessions (re-exported as FastAPI dependencies) ---


async def db_session() -> AsyncIterator[AsyncSession]:
    async for s in get_session():
        yield s


async def manager_db_session() -> AsyncIterator[AsyncSession]:
    async for s in get_manager_session():
        yield s


# --- Tenant context dependencies ---

_bearer = HTTPBearer(auto_error=False)


@dataclass(slots=True)
class WidgetTokenContext:
    tenant_id: str
    widget_id: str
    origin: str
    visitor_session: str | None


def get_current_tenant_id() -> str:
    tid = tenant_id_ctx.get()
    if tid is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "missing tenant context")
    return tid


async def get_current_widget_context(
    origin: str | None = Header(default=None),
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
    signer: PyJWTSigner = Depends(get_token_signer),
) -> AsyncIterator[WidgetTokenContext]:
    if creds is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "missing widget token")
    try:
        claims = signer.verify_token(creds.credentials)
    except jwt.PyJWTError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid widget token") from exc

    issued_origin = str(claims.get("origin", ""))
    if origin is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "missing origin")
    if origin != issued_origin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "origin mismatch")

    tenant_id = claims.get("tenant_id")
    if tenant_id is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "missing tenant claim")
    widget_id = claims.get("widget_id")
    if widget_id is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "missing widget claim")

    token = set_tenant_id(str(tenant_id))
    try:
        yield WidgetTokenContext(
            tenant_id=str(tenant_id),
            widget_id=str(widget_id),
            origin=issued_origin,
            visitor_session=claims.get("visitor_session"),
        )
    finally:
        reset_tenant_id(token)


def get_current_widget_tenant_id(
    widget_context: WidgetTokenContext = Depends(get_current_widget_context),
) -> str:
    return widget_context.tenant_id


def require_matching_tenant(body_tenant_id: UUID | str | None) -> None:
    """Reject requests whose body/path claims a tenant different from the token's.

    The token always wins. A request with no token context cannot assert a tenant.
    """
    ctx = tenant_id_ctx.get()
    if body_tenant_id is None:
        return
    if ctx is None or str(body_tenant_id) != str(ctx):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "tenant mismatch")


# --- Manager-surface composition (single shared session per request) ---


@dataclass(slots=True)
class ManagerContext:
    session: AsyncSession
    tenants: PostgresTenantRepository
    users: PostgresUserRepository
    invitations: PostgresInvitationRepository
    audit: PostgresAuditRepository
    provision: ProvisionTenantUseCase
    erase: EraseTenantUseCase
    invite: InviteAdminUseCase


async def get_manager_context(
    session: AsyncSession = Depends(manager_db_session),
    session_store: SessionStore = Depends(get_session_store),
    object_storage: MinIOObjectStorage = Depends(get_object_storage),
) -> ManagerContext:
    """Builds all Owner-A repos + use cases on ONE concierge_manager session so a
    provisioning request (tenant + widget + origins + invitation + audit) commits
    atomically. Used by the manager routes and the public invitation-accept route
    (both need the elevated role's grants). frameworks→use_cases/adapters imports
    are allowed by the dependency rule (outer may import inner)."""
    settings = get_settings()
    tenants = PostgresTenantRepository(session)
    users = PostgresUserRepository(session)
    invitations = PostgresInvitationRepository(session)
    audit = PostgresAuditRepository(session)
    invite = InviteAdminUseCase(
        invitations,
        ConsoleEmailSender(),
        ttl_hours=settings.invitation_ttl_hours,
        accept_url_base=settings.public_base_url,
    )
    provision = ProvisionTenantUseCase(tenants, audit, invite)
    erase = EraseTenantUseCase(tenants, audit, session_store, object_storage)
    return ManagerContext(
        session=session,
        tenants=tenants,
        users=users,
        invitations=invitations,
        audit=audit,
        provision=provision,
        erase=erase,
        invite=invite,
    )
