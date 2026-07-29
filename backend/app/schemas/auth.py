"""
schemas/auth.py
===============
Pydantic v2 request and response schemas for authentication endpoints.

Security contract:
- UserResponse MUST NOT include hashed_password.
- Password fields in UserCreate / UserUpdate are write-only; they are never
  included in any response schema.
- The JWT access token is delivered ONLY via an HttpOnly cookie — it is never
  returned in the JSON response body.
- CSRF token is included in cookie-based responses so the frontend can store
  it for subsequent state-mutating requests.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from email_validator import EmailNotValidError, validate_email
from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.user import UserRole


# ---------------------------------------------------------------------------
# Request schemas
# ---------------------------------------------------------------------------


def _validate_email(value: str) -> str:
    try:
        validated = validate_email(value, test_environment=True)
    except EmailNotValidError as exc:
        raise ValueError(str(exc))
    return validated.email


class LoginRequest(BaseModel):
    email: str
    password: str

    @field_validator('email')
    @classmethod
    def validate_email(cls, value: str) -> str:
        return _validate_email(value)


class UserCreate(BaseModel):
    """Body for POST /users (ADMIN only). Creates a new user account."""

    email: str
    password: str = Field(min_length=12, max_length=128)
    full_name: Optional[str] = None
    role: UserRole

    @field_validator('email')
    @classmethod
    def validate_email(cls, value: str) -> str:
        return _validate_email(value)


class UserUpdate(BaseModel):
    """Body for PATCH /users/{id} (ADMIN only). All fields are optional."""

    full_name: Optional[str] = None
    role: Optional[UserRole] = None
    is_active: Optional[bool] = None
    password: Optional[str] = Field(default=None, min_length=12, max_length=128)


# ---------------------------------------------------------------------------
# User representation (safe — no hashed_password)
# ---------------------------------------------------------------------------


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    full_name: Optional[str]
    role: UserRole
    is_active: bool
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------


class LoginResponse(BaseModel):
    """Extended login response: user info + CSRF token + expiry hint.

    The JWT access token is delivered exclusively via an HttpOnly cookie
    (set on the Response object by the login endpoint). It is intentionally
    absent from this JSON body so that JavaScript cannot read or store it.

    The frontend needs only:
    - ``user``       — authenticated user object (avoids a second GET /me call).
    - ``csrf_token`` — must be stored in JS for state-mutating requests.
    - ``expires_in`` — seconds until the cookie expires (for UX scheduling).
    """

    user: UserResponse
    expires_in: int   # seconds until access token expires
    csrf_token: str   # CSRF token — must be stored in JS (not HttpOnly)


class CurrentUserResponse(BaseModel):
    """Returned by GET /auth/me."""

    user: UserResponse
    csrf_token: str   # CSRF token refreshed/restored from cookie


class MessageResponse(BaseModel):
    """Generic message envelope (e.g., for logout)."""

    message: str
