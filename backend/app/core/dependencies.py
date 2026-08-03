"""
core/dependencies.py
====================
FastAPI dependency callables for authentication and role-based authorization.

Security contract
-----------------
- The JWT access token is read ONLY from the HttpOnly cookie named
  settings.AUTH_COOKIE_NAME.  It is NEVER read from the Authorization header.
- The user's role is ALWAYS sourced from the database — never trusted from the
  JWT payload — so a stale or forged role claim cannot escalate privileges.
- All authentication failure modes (missing cookie, malformed token, expired
  token, invalid signature, user not found, inactive user) produce the
  IDENTICAL HTTP 401 response to prevent information leakage.
- CSRF tokens are validated using constant-time comparison (hmac.compare_digest)
  to prevent timing attacks.  Token values are NEVER logged.
"""

from __future__ import annotations

import hmac
from typing import Callable

from app.core.config import settings
from app.core.security import InvalidTokenError, decode_access_token
from app.db.session import get_db
from app.models.user import User, UserRole
from app.services.auth_service import AuthService, InvalidCredentialsError, UserNotFoundError
from fastapi import Cookie, Depends, Header, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession

# ---------------------------------------------------------------------------
# Shared 401 response
# ---------------------------------------------------------------------------

# A module-level constant ensures ALL authentication failure paths return an
# identical response — body, status code, and WWW-Authenticate header — so
# no information is leaked about which step failed.
_AUTH_REQUIRED = HTTPException(
    status_code=status.HTTP_401_UNAUTHORIZED,
    detail="Authentication required.",
    headers={"WWW-Authenticate": "Bearer"},
)


# ---------------------------------------------------------------------------
# get_current_user
# ---------------------------------------------------------------------------


async def get_current_user(
    db: AsyncSession = Depends(get_db),
    token: str | None = Cookie(default=None, alias=settings.AUTH_COOKIE_NAME),
) -> User:
    """FastAPI dependency: extract JWT from the auth cookie, validate it,
    load the authoritative User from the database, and return it.

    Raises HTTP 401 (_AUTH_REQUIRED) for ALL of:
    - missing cookie
    - malformed token
    - expired token
    - invalid signature
    - user not found
    - inactive user

    NEVER leaks:
    - JWT decode details
    - whether the user exists
    - database details
    """
    if token is None:
        raise _AUTH_REQUIRED

    try:
        payload = decode_access_token(token)
    except InvalidTokenError:
        raise _AUTH_REQUIRED

    try:
        svc = AuthService(db)
        user = await svc.get_current_user(payload.sub)
    except (UserNotFoundError, InvalidCredentialsError):
        raise _AUTH_REQUIRED

    return user


# ---------------------------------------------------------------------------
# require_roles factory
# ---------------------------------------------------------------------------


def require_roles(*allowed_roles: UserRole) -> Callable:
    """Return a FastAPI dependency that enforces role-based access control.

    The returned dependency:
    - Calls get_current_user (handles authentication).
    - Checks current_user.role against allowed_roles (from DB — authoritative).
    - Returns the User if authorized.
    - Raises HTTP 403 if the user's DB role is not in allowed_roles.

    Usage::

        @router.post("/admin-only")
        async def admin_only(
            user: User = Depends(require_roles(UserRole.ADMIN))
        ): ...
    """

    async def dependency(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Insufficient permissions.",
            )
        return current_user

    return dependency


# ---------------------------------------------------------------------------
# Convenience aliases
# ---------------------------------------------------------------------------

# Any authenticated user — use for endpoints open to all roles.
require_any_authenticated_user = get_current_user

# DATA_MANAGER or ADMIN — for data import endpoints.
require_data_manager_or_admin = require_roles(UserRole.ADMIN, UserRole.DATA_MANAGER)

# ADMIN only — for user management endpoints.
require_admin = require_roles(UserRole.ADMIN)


# ---------------------------------------------------------------------------
# validate_csrf
# ---------------------------------------------------------------------------

# Shared 403 response for all CSRF failure modes.  A single constant ensures
# all failure paths return an IDENTICAL response — status, body, and headers —
# so no information is leaked about *which* check failed (missing cookie,
# missing header, or mismatch).
_CSRF_FAIL = HTTPException(
    status_code=status.HTTP_403_FORBIDDEN,
    detail="CSRF validation failed.",
)


async def validate_csrf(
    request: Request,
    csrf_cookie: str | None = Cookie(default=None, alias=settings.CSRF_COOKIE_NAME),
    csrf_header: str | None = Header(default=None, alias=settings.CSRF_HEADER_NAME),
) -> None:
    """Enforce CSRF for unsafe HTTP methods (POST, PUT, PATCH, DELETE).

    Compares the CSRF cookie value against the X-CSRF-Token request header
    using constant-time comparison (hmac.compare_digest) to prevent timing
    attacks.

    Raises HTTP 403 for:
    - Missing cookie
    - Missing header
    - Blank values
    - Mismatched values

    Safe methods (GET, HEAD, OPTIONS) are passed through without checking.
    Token values are NEVER logged.
    """
    if request.method.upper() in ("GET", "HEAD", "OPTIONS"):
        return None

    if not csrf_cookie or not csrf_cookie.strip():
        raise _CSRF_FAIL
    if not csrf_header or not csrf_header.strip():
        raise _CSRF_FAIL

    if not hmac.compare_digest(csrf_cookie.strip(), csrf_header.strip()):
        raise _CSRF_FAIL

    return None
