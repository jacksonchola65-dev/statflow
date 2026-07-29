"""
auth_service.py
===============
Authentication and user lifecycle service for StatFlow.

Design constraints
------------------
- Does NOT call session.commit() or session.rollback().
  The endpoint / dependency layer owns the transaction boundary.
- Does NOT expose PyJWT, pwdlib, or SQLAlchemy internals to callers.
  All library-specific exceptions are caught and translated into
  the stable domain exceptions defined below.
- Plaintext passwords are never logged, stored, or surfaced.
- All three authenticate() failure modes (unknown email, wrong password,
  inactive account) produce the identical InvalidCredentialsError message
  to prevent user-enumeration attacks.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import create_access_token, hash_password, verify_password
from app.models.user import User, UserRole
from app.repositories.user_repository import UserRepository


# ---------------------------------------------------------------------------
# Domain exceptions
# ---------------------------------------------------------------------------


class InvalidCredentialsError(Exception):
    """Raised when email/password authentication fails for any reason."""


class EmailAlreadyExistsError(Exception):
    """Raised when attempting to create a user with a duplicate email."""


class PasswordPolicyError(Exception):
    """Raised when a password does not meet the minimum policy requirements."""


class UserNotFoundError(Exception):
    """Raised when a required user cannot be found in the database."""


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AuthenticatedUser:
    """Returned by AuthService.authenticate() on success."""

    user: User          # the full User ORM object
    access_token: str   # signed JWT string


# ---------------------------------------------------------------------------
# Private helpers
# ---------------------------------------------------------------------------


def _validate_password_policy(password: str) -> None:
    """Raise PasswordPolicyError if *password* does not meet policy requirements.

    Rules enforced:
    - Must not be blank or whitespace-only.
    - Must be at least 12 characters long.
    - Must be at most 128 characters long.

    Notably NOT required: uppercase letters, digits, or symbols.
    A valid 12+ character passphrase of any printable characters is accepted.
    """
    if not password or not password.strip():
        raise PasswordPolicyError(
            "Password must not be blank or consist entirely of whitespace."
        )
    if len(password) < 12:
        raise PasswordPolicyError(
            "Password must be at least 12 characters long."
        )
    if len(password) > 128:
        raise PasswordPolicyError(
            "Password must not exceed 128 characters."
        )


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class AuthService:
    """Handles authentication and user lifecycle operations."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._repo = UserRepository(session)

    # ------------------------------------------------------------------
    # authenticate
    # ------------------------------------------------------------------

    async def authenticate(self, email: str, password: str) -> AuthenticatedUser:
        """Authenticate a user by email and password.

        Returns an AuthenticatedUser with a signed JWT on success.

        Raises:
            InvalidCredentialsError: If the email is not found, the account is
                inactive, or the password does not match. All three cases
                produce the *identical* message to prevent user enumeration.
        """
        _GENERIC_ERROR = InvalidCredentialsError("Invalid credentials.")

        user = await self._repo.get_by_email(email)
        if user is None:
            raise _GENERIC_ERROR

        if not user.is_active:
            raise _GENERIC_ERROR

        if not verify_password(password, user.hashed_password):
            raise _GENERIC_ERROR

        token = create_access_token(user_id=user.id, role=user.role, email=user.email)
        return AuthenticatedUser(user=user, access_token=token)

    # ------------------------------------------------------------------
    # create_user
    # ------------------------------------------------------------------

    async def create_user(
        self,
        email: str,
        password: str,
        full_name: str | None,
        role: UserRole,
        is_active: bool = True,
    ) -> User:
        """Create a new user account.

        Validates the password policy, checks for duplicate email, hashes the
        password, and delegates persistence to the repository.

        Raises:
            PasswordPolicyError: If *password* does not meet policy requirements.
            EmailAlreadyExistsError: If *email* (case-insensitive) already exists.
        """
        # 1. Policy check first — fail fast before any DB round-trip.
        _validate_password_policy(password)

        # 2. Duplicate email check (case-insensitive, handled by repository).
        if await self._repo.email_exists(email):
            raise EmailAlreadyExistsError("A user with that email already exists.")

        # 3. Hash the password. Plaintext is never passed to the repository.
        hashed = hash_password(password)

        # 4. Persist via repository (which calls flush, not commit).
        user = await self._repo.create_user(
            email=email,
            hashed_password=hashed,
            full_name=full_name,
            role=role,
            is_active=is_active,
        )

        return user

    # ------------------------------------------------------------------
    # change_password
    # ------------------------------------------------------------------

    async def change_password(self, user_id: uuid.UUID, new_password: str) -> User:
        """Update the password for an existing user.

        Raises:
            UserNotFoundError: If no user exists with *user_id*.
            PasswordPolicyError: If *new_password* does not meet policy requirements.
        """
        user = await self._repo.get_by_id(user_id)
        if user is None:
            raise UserNotFoundError("User not found.")

        # Validate policy before hashing.
        _validate_password_policy(new_password)

        hashed = hash_password(new_password)

        # update_user returns None only when the user is not found, but we
        # already verified existence above, so the result is always a User.
        updated = await self._repo.update_user(user_id, hashed_password=hashed)
        assert updated is not None  # defensive; should never be None here
        return updated

    # ------------------------------------------------------------------
    # get_current_user
    # ------------------------------------------------------------------

    async def get_current_user(self, user_id: uuid.UUID) -> User:
        """Load and return the active user identified by *user_id*.

        The JWT role claim is intentionally NOT used here; the authoritative
        role is always fetched from the database.

        Raises:
            UserNotFoundError: If no user exists with *user_id*.
            InvalidCredentialsError: If the user exists but is inactive.
        """
        user = await self._repo.get_by_id(user_id)
        if user is None:
            raise UserNotFoundError("User not found.")

        if not user.is_active:
            # Using InvalidCredentialsError for inactive accounts.
            # The dependency layer should catch this alongside UserNotFoundError
            # and map both to HTTP 401.
            raise InvalidCredentialsError("Invalid credentials.")

        return user
