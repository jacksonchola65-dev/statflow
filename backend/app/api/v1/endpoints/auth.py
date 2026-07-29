"""
api/v1/endpoints/auth.py
========================
Authentication endpoints: login, /me, logout.

Security contract
-----------------
- The JWT access token is delivered ONLY via an HttpOnly cookie
  (settings.AUTH_COOKIE_NAME). It is NOT returned in the JSON response body.
- A separate CSRF cookie (not HttpOnly) is issued alongside the auth cookie
  so that the frontend can read it and include it in state-mutating requests.
- Logout is safe and idempotent: it clears both cookies regardless of whether
  they are present, and requires no JWT.
- All login failure modes (unknown email, wrong password, inactive account)
  produce the identical 401 response to prevent user enumeration (REQ-4.2).
"""

from __future__ import annotations

import secrets

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.dependencies import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.auth import (
    CurrentUserResponse,
    LoginRequest,
    LoginResponse,
    MessageResponse,
    UserResponse,
)
from app.services.auth_service import AuthService, InvalidCredentialsError

router = APIRouter(prefix="/auth", tags=["auth"])


# ---------------------------------------------------------------------------
# POST /auth/login
# ---------------------------------------------------------------------------


@router.post("/login", response_model=LoginResponse)
async def login(
    body: LoginRequest,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> LoginResponse:
    """Authenticate with email and password.

    On success:
    - Returns ``{ user, expires_in, csrf_token }`` in the response body.
    - Sets two cookies:
        - **Auth cookie** (HttpOnly): carries the JWT access token.
          The JWT is NOT in the JSON body.
        - **CSRF cookie** (not HttpOnly): carries a CSRF token readable by JS.

    On failure (wrong email, wrong password, inactive account):
    - Returns HTTP 401 with ``{ "detail": "Invalid credentials." }`` (REQ-4.2).
    """
    svc = AuthService(db)

    try:
        result = await svc.authenticate(body.email, body.password)
    except InvalidCredentialsError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials.",
        )

    csrf_token = secrets.token_urlsafe(32)

    # Auth cookie — HttpOnly so JS cannot read the JWT.
    response.set_cookie(
        key=settings.AUTH_COOKIE_NAME,
        value=result.access_token,
        httponly=True,
        secure=settings.COOKIE_SECURE,
        samesite=settings.COOKIE_SAMESITE,
        path="/",
        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )

    # CSRF cookie — NOT HttpOnly so the frontend can read it.
    response.set_cookie(
        key=settings.CSRF_COOKIE_NAME,
        value=csrf_token,
        httponly=False,
        secure=settings.COOKIE_SECURE,
        samesite=settings.COOKIE_SAMESITE,
        path="/",
        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )

    return LoginResponse(
        user=UserResponse.model_validate(result.user),
        expires_in=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        csrf_token=csrf_token,
    )


# ---------------------------------------------------------------------------
# GET /auth/me
# ---------------------------------------------------------------------------


@router.get("/me", response_model=CurrentUserResponse)
async def me(
    response: Response,
    current_user: User = Depends(get_current_user),
) -> CurrentUserResponse:
    """Return the currently authenticated user (REQ-4.6).

    Requires a valid JWT — either via the HttpOnly auth cookie or the
    Authorization: Bearer header (handled transparently by get_current_user).

    Returns: ``{ user: { id, email, full_name, role, is_active,
                          created_at, updated_at }, csrf_token }``

    The auth cookie lifetime is NOT extended here — no new JWT is issued.
    The CSRF cookie is refreshed (new value, extended lifetime) so that
    long-lived sessions stay protected.
    """
    # Refresh the CSRF token (new random value, extended max_age).
    csrf_token = secrets.token_urlsafe(32)
    response.set_cookie(
        key=settings.CSRF_COOKIE_NAME,
        value=csrf_token,
        httponly=False,
        secure=settings.COOKIE_SECURE,
        samesite=settings.COOKIE_SAMESITE,
        path="/",
        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )

    return CurrentUserResponse(
        user=UserResponse.model_validate(current_user),
        csrf_token=csrf_token,
    )


# ---------------------------------------------------------------------------
# POST /auth/logout
# ---------------------------------------------------------------------------


@router.post("/logout", response_model=MessageResponse)
async def logout(response: Response) -> MessageResponse:
    """Clear the auth and CSRF cookies.

    Safe and idempotent — works even when no cookies are present.
    No JWT or database access required.
    """
    response.delete_cookie(
        key=settings.AUTH_COOKIE_NAME,
        path="/",
        secure=settings.COOKIE_SECURE,
        samesite=settings.COOKIE_SAMESITE,
    )
    response.delete_cookie(
        key=settings.CSRF_COOKIE_NAME,
        path="/",
        secure=settings.COOKIE_SECURE,
        samesite=settings.COOKIE_SAMESITE,
    )

    return MessageResponse(message="Logged out.")
