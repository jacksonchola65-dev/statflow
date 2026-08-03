"""
user_repository.py
==================
Data access layer for User entities.

Design constraints
------------------
- Follows the StatFlow repository pattern:
    class FooRepository:
        def __init__(self, session: AsyncSession) -> None: ...
- Methods NEVER call session.commit() or session.rollback().
  The service layer owns the transaction boundary.
- session.flush() IS used inside create_user so the generated id is
  available to callers immediately after creation.
- No business logic (no last-admin enforcement, no password hashing).
- No FastAPI HTTP exceptions — only data access.
- Email normalization is centralised in _normalize_email(); never duplicated.
"""

from __future__ import annotations

import uuid

from app.models.user import User, UserRole
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

# ---------------------------------------------------------------------------
# Private helper
# ---------------------------------------------------------------------------


def _normalize_email(email: str) -> str:
    """Strip surrounding whitespace and lower-case an email address."""
    return email.strip().lower()


# ---------------------------------------------------------------------------
# Repository
# ---------------------------------------------------------------------------


class UserRepository:
    """Data access layer used by the auth service and user management service."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ------------------------------------------------------------------
    # Read operations
    # ------------------------------------------------------------------

    async def get_by_id(self, user_id: uuid.UUID) -> User | None:
        """Return user by primary key, or None if not found."""
        result = await self._session.execute(select(User).where(User.id == user_id))
        return result.scalar_one_or_none()

    async def get_by_email(self, email: str) -> User | None:
        """
        Return user by email (case-insensitive, whitespace-stripped), or None.

        Normalisation is applied on both the stored value (via DB functions)
        and the lookup value (via _normalize_email) so the comparison is
        always performed on the same canonical form.
        """
        result = await self._session.execute(
            select(User).where(func.lower(func.trim(User.email)) == _normalize_email(email))
        )
        return result.scalar_one_or_none()

    async def list_users(self, skip: int = 0, limit: int = 100) -> list[User]:
        """
        Return a paginated slice of users ordered by created_at ASC, then id ASC
        (deterministic ordering for consistent pagination).

        Args:
            skip:  Number of rows to skip (offset). Defaults to 0.
            limit: Maximum number of rows to return. Defaults to 100.
        """
        result = await self._session.execute(
            select(User).order_by(User.created_at.asc(), User.id.asc()).offset(skip).limit(limit)
        )
        return list(result.scalars().all())

    async def count_active_admins(self) -> int:
        """
        Count users where role == ADMIN AND is_active == True.

        The service layer enforces the last-admin rule using this count;
        the repository only provides the number.
        """
        result = await self._session.execute(
            select(func.count())
            .select_from(User)
            .where(
                User.role == UserRole.ADMIN,
                User.is_active.is_(True),
            )
        )
        return result.scalar_one()

    async def email_exists(
        self,
        email: str,
        exclude_user_id: uuid.UUID | None = None,
    ) -> bool:
        """
        Return True if the normalized email already exists in the database.

        If exclude_user_id is provided, that user's row is ignored — useful
        when checking whether a new email is free during an update operation.
        """
        stmt = (
            select(func.count())
            .select_from(User)
            .where(func.lower(func.trim(User.email)) == _normalize_email(email))
        )
        if exclude_user_id is not None:
            stmt = stmt.where(User.id != exclude_user_id)

        result = await self._session.execute(stmt)
        return result.scalar_one() > 0

    # ------------------------------------------------------------------
    # Write operations
    # ------------------------------------------------------------------

    async def create_user(
        self,
        email: str,
        hashed_password: str,
        full_name: str | None,
        role: UserRole,
        is_active: bool = True,
    ) -> User:
        """
        Create a new User row.

        - Normalizes email before storing.
        - Calls session.flush() so the generated id is available immediately.
        - Does NOT commit.

        The caller is responsible for hashing the password before passing it;
        this repository never hashes passwords.
        """
        user = User(
            email=_normalize_email(email),
            hashed_password=hashed_password,
            full_name=full_name,
            role=role,
            is_active=is_active,
        )
        self._session.add(user)
        await self._session.flush()  # populates user.id
        return user

    async def update_user(
        self,
        user_id: uuid.UUID,
        *,
        email: str | None = None,
        full_name: str | None = None,
        role: UserRole | None = None,
        is_active: bool | None = None,
        hashed_password: str | None = None,
    ) -> User | None:
        """
        Apply only the explicitly provided keyword arguments to the User.

        - Email is normalized when being changed.
        - Does NOT commit.
        - Returns the updated User, or None if the user was not found.
        """
        user = await self.get_by_id(user_id)
        if user is None:
            return None

        if email is not None:
            user.email = _normalize_email(email)
        if full_name is not None:
            user.full_name = full_name
        if role is not None:
            user.role = role
        if is_active is not None:
            user.is_active = is_active
        if hashed_password is not None:
            user.hashed_password = hashed_password

        return user

    async def deactivate_user(self, user_id: uuid.UUID) -> User | None:
        """
        Set is_active = False on the specified user (soft-delete).

        - Does NOT commit.
        - Returns the updated User, or None if the user was not found.
        """
        user = await self.get_by_id(user_id)
        if user is None:
            return None

        user.is_active = False
        return user
