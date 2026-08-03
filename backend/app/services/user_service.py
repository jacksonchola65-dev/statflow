"""
user_service.py
===============
User management service for StatFlow.

Design constraints
------------------
- Does NOT call session.commit() or session.rollback().
  The endpoint layer owns the transaction boundary (via get_db auto-commit).
- Reuses password policy validation and domain exceptions from auth_service.
- Enforces last-active-admin invariant for role demotions, deactivations, and
  soft deletes.
- Enforces self-deletion prevention for ADMIN users.
- Soft-delete only: users are marked is_active=False, never removed from DB.
"""

from __future__ import annotations

import uuid

from app.core.security import hash_password
from app.models.user import User, UserRole
from app.repositories.user_repository import UserRepository
from app.services.auth_service import (
    EmailAlreadyExistsError,
    UserNotFoundError,
    _validate_password_policy,
)
from sqlalchemy.ext.asyncio import AsyncSession

# ---------------------------------------------------------------------------
# Domain exceptions
# ---------------------------------------------------------------------------


class LastActiveAdminError(Exception):
    """Raised when an operation would leave zero active ADMIN users."""


class SelfDeletionError(Exception):
    """Raised when an ADMIN attempts to delete their own account."""


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class UserService:
    """Handles user CRUD operations with business-rule enforcement."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._repo = UserRepository(session)

    # ------------------------------------------------------------------
    # list_users
    # ------------------------------------------------------------------

    async def list_users(self) -> list[User]:
        """Return all users ordered by created_at ASC, then id ASC."""
        return await self._repo.list_users()

    # ------------------------------------------------------------------
    # get_user
    # ------------------------------------------------------------------

    async def get_user(self, user_id: uuid.UUID) -> User:
        """Load and return a user by primary key.

        Raises:
            UserNotFoundError: If no user exists with *user_id*.
        """
        user = await self._repo.get_by_id(user_id)
        if user is None:
            raise UserNotFoundError("User not found.")
        return user

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

        Steps:
        1. Validate password policy.
        2. Check for duplicate email.
        3. Hash password (plaintext never reaches the repository).
        4. Persist via repository.

        Raises:
            PasswordPolicyError: If *password* does not meet policy requirements.
            EmailAlreadyExistsError: If *email* already exists (case-insensitive).
        """
        _validate_password_policy(password)

        if await self._repo.email_exists(email):
            raise EmailAlreadyExistsError("A user with that email already exists.")

        hashed = hash_password(password)

        return await self._repo.create_user(
            email=email,
            hashed_password=hashed,
            full_name=full_name,
            role=role,
            is_active=is_active,
        )

    # ------------------------------------------------------------------
    # update_user
    # ------------------------------------------------------------------

    async def update_user(
        self,
        user_id: uuid.UUID,
        *,
        email: str | None = None,
        full_name: str | None = None,
        role: UserRole | None = None,
        is_active: bool | None = None,
        password: str | None = None,
    ) -> User:
        """Apply a partial update to an existing user.

        Only fields explicitly provided (non-None) are updated.

        Last-admin check: if the target user is currently an active ADMIN, and
        the update would demote them (role → non-ADMIN) or deactivate them
        (is_active → False), the operation is rejected when they are the last
        active admin.

        Raises:
            UserNotFoundError: If no user exists with *user_id*.
            EmailAlreadyExistsError: If *email* already exists for another user.
            LastActiveAdminError: If the update would leave zero active admins.
            PasswordPolicyError: If *password* does not meet policy requirements.
        """
        user = await self._repo.get_by_id(user_id)
        if user is None:
            raise UserNotFoundError("User not found.")

        # Email uniqueness check (exclude current user's own email).
        if email is not None:
            if await self._repo.email_exists(email, exclude_user_id=user_id):
                raise EmailAlreadyExistsError("A user with that email already exists.")

        # Last-admin check: only relevant when the target is currently ADMIN+active.
        if user.role == UserRole.ADMIN and user.is_active:
            demoting = role is not None and role != UserRole.ADMIN
            deactivating = is_active is not None and is_active is False
            if demoting or deactivating:
                count = await self._repo.count_active_admins()
                if count <= 1:
                    raise LastActiveAdminError("At least one active administrator must remain.")

        # Password: validate policy and hash if provided.
        hashed: str | None = None
        if password is not None:
            _validate_password_policy(password)
            hashed = hash_password(password)

        updated = await self._repo.update_user(
            user_id,
            email=email,
            full_name=full_name,
            role=role,
            is_active=is_active,
            hashed_password=hashed,
        )

        # update_user returns None only if user doesn't exist; we checked above.
        assert updated is not None
        return updated

    # ------------------------------------------------------------------
    # delete_user
    # ------------------------------------------------------------------

    async def delete_user(
        self,
        user_id: uuid.UUID,
        acting_user_id: uuid.UUID,
    ) -> None:
        """Soft-delete a user by marking is_active=False.

        The user row is NEVER physically removed.

        Raises:
            UserNotFoundError: If no user exists with *user_id*.
            SelfDeletionError: If *acting_user_id* matches *user_id*.
            LastActiveAdminError: If deleting would leave zero active admins.
        """
        user = await self._repo.get_by_id(user_id)
        if user is None:
            raise UserNotFoundError("User not found.")

        if user_id == acting_user_id:
            raise SelfDeletionError("You cannot delete your own account.")

        if user.role == UserRole.ADMIN and user.is_active:
            count = await self._repo.count_active_admins()
            if count <= 1:
                raise LastActiveAdminError("At least one active administrator must remain.")

        await self._repo.update_user(user_id, is_active=False)
