"""
schemas/users.py
================
Pydantic v2 schemas for user management endpoints.

Security contract:
- UserResponse (imported from schemas/auth.py) MUST NOT include hashed_password.
- UserUpdateRequest uses None as sentinel for "not supplied / unchanged".
"""

from __future__ import annotations

from app.models.user import UserRole
from app.schemas.auth import UserResponse  # noqa: F401 — re-exported for convenience
from email_validator import EmailNotValidError, validate_email
from pydantic import BaseModel, ConfigDict, field_validator

# ---------------------------------------------------------------------------
# Request schemas
# ---------------------------------------------------------------------------


def _validate_email(value: str) -> str:
    try:
        validated = validate_email(value, test_environment=True)
    except EmailNotValidError as exc:
        raise ValueError(str(exc))
    return validated.email


class UserCreateRequest(BaseModel):
    email: str
    password: str
    full_name: str | None = None
    role: UserRole = UserRole.VIEWER
    is_active: bool = True

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        return _validate_email(value)


class UserUpdateRequest(BaseModel):
    """Partial-update schema.

    Every field defaults to None, which means "not supplied — leave unchanged".
    To explicitly set a value, pass the desired value. To clear full_name in a
    future enhancement, a dedicated endpoint would be used.
    """

    email: str | None = None
    full_name: str | None = None
    role: UserRole | None = None
    is_active: bool | None = None
    password: str | None = None

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return _validate_email(value)


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------


class UserListResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    users: list[UserResponse]
    total: int
