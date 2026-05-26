"""Session auth for the admin/manager surface (supports T113).

Password hashing reuses fastapi-users' PasswordHelper (Argon2id). Sessions are
short HS256 JWTs signed with `settings.session_secret`, carrying the principal's
user id, role, and (for tenant_admin) tenant id. This is the verified-token source
the rest of the app trusts; the body is never trusted for identity.

Note: the full fastapi-users register/password-reset/email-verify routers are a
follow-up within T113; this module provides the login + principal plumbing the
manager surface and invitation-acceptance flow need now.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi_users.password import PasswordHelper

from app.entities.user import UserRole
from app.frameworks.config import Settings, get_settings

_password_helper = PasswordHelper()
_bearer = HTTPBearer(auto_error=False)
_ALGO = "HS256"
_SESSION_TTL = timedelta(hours=12)


def hash_password(plain: str) -> str:
    return _password_helper.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    ok, _ = _password_helper.verify_and_update(plain, hashed)
    return ok


@dataclass(slots=True)
class Principal:
    user_id: str
    role: UserRole
    tenant_id: str | None = None


def issue_session_token(principal: Principal, settings: Settings | None = None) -> str:
    settings = settings or get_settings()
    now = datetime.now(timezone.utc)
    claims = {
        "sub": principal.user_id,
        "role": principal.role.value,
        "iat": now,
        "exp": now + _SESSION_TTL,
    }
    if principal.tenant_id is not None:
        claims["tenant_id"] = principal.tenant_id
    return jwt.encode(claims, settings.session_secret, algorithm=_ALGO)


def decode_session_token(token: str, settings: Settings | None = None) -> Principal:
    settings = settings or get_settings()
    try:
        claims = jwt.decode(token, settings.session_secret, algorithms=[_ALGO])
    except jwt.PyJWTError as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid session token") from exc
    return Principal(
        user_id=claims["sub"],
        role=UserRole(claims["role"]),
        tenant_id=claims.get("tenant_id"),
    )


def get_principal(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> Principal:
    if creds is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "missing credentials")
    return decode_session_token(creds.credentials)


def require_manager(principal: Principal = Depends(get_principal)) -> Principal:
    if principal.role is not UserRole.TENANT_MANAGER:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "tenant_manager role required")
    return principal
