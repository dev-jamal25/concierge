"""Auth routes (T113 login + T114 invitation acceptance) — Owner A.

Login and invitation acceptance run under the elevated concierge_manager session
(the only role granted reads/writes on users + user_tenant_roles). Identity always
comes from the verified token afterwards, never from request bodies.

Full fastapi-users register/password-reset/email-verify routers are a follow-up
within T113; password hashing here already uses fastapi-users' PasswordHelper.
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr

from app.entities.audit_entry import AuditOutcome
from app.entities.user import UserRole
from app.frameworks.api.deps import ManagerContext, get_manager_context
from app.frameworks.api.session_auth import (
    Principal,
    get_principal,
    hash_password,
    issue_session_token,
    verify_password,
)
from app.use_cases.invitation_tokens import hash_token

router = APIRouter(prefix="/auth", tags=["auth"])


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class MeResponse(BaseModel):
    user_id: str
    email: str
    role: str
    tenant_id: str | None = None


class AcceptInvitationRequest(BaseModel):
    password: str


@router.post("/login", response_model=TokenResponse)
async def login(
    body: LoginRequest, ctx: ManagerContext = Depends(get_manager_context)
) -> TokenResponse:
    user = await ctx.users.get_by_email(body.email)
    if user is None or not user.is_active or not verify_password(body.password, user.hashed_password):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid credentials")

    tenant_id: str | None = None
    if user.role is UserRole.TENANT_ADMIN:
        tid = await ctx.users.primary_tenant_id(user.id)
        tenant_id = str(tid) if tid else None

    principal = Principal(user_id=str(user.id), role=user.role, tenant_id=tenant_id)
    return TokenResponse(access_token=issue_session_token(principal))


@router.post(
    "/invitations/{token}/accept",
    response_model=TokenResponse,
    status_code=status.HTTP_201_CREATED,
)
async def accept_invitation(
    token: str,
    body: AcceptInvitationRequest,
    ctx: ManagerContext = Depends(get_manager_context),
) -> TokenResponse:
    invitation = await ctx.invitations.get_pending_by_token_hash(hash_token(token))
    if invitation is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "invitation not found or expired")

    existing = await ctx.users.get_by_email(invitation.email)
    if existing is not None:
        user_id: UUID = existing.id
    else:
        created = await ctx.users.create(
            email=invitation.email,
            hashed_password=hash_password(body.password),
            role=UserRole.TENANT_ADMIN,
        )
        user_id = created.id

    await ctx.users.bind_tenant_role(user_id, invitation.tenant_id)
    await ctx.invitations.mark_accepted(invitation.id)
    await ctx.audit.log(
        action="invitation_accept",
        outcome=AuditOutcome.SUCCESS,
        actor_user_id=user_id,
        target_tenant_id=invitation.tenant_id,
        details={"email": invitation.email},
    )

    principal = Principal(
        user_id=str(user_id), role=UserRole.TENANT_ADMIN, tenant_id=str(invitation.tenant_id)
    )
    return TokenResponse(access_token=issue_session_token(principal))


@router.get("/me", response_model=MeResponse)
async def me(
    principal: Principal = Depends(get_principal),
    ctx: ManagerContext = Depends(get_manager_context),
) -> MeResponse:
    """Return the identity of the authenticated session token.

    Safe fields only: user_id, email, role, tenant_id. No password hash or secrets.
    Returns 401 if the token is invalid, expired, or the user no longer exists.
    """
    user = await ctx.users.get(UUID(principal.user_id))
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "user not found")
    return MeResponse(
        user_id=str(user.id),
        email=user.email,
        role=principal.role.value,
        tenant_id=principal.tenant_id,
    )
