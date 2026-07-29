"""
test_user_repository.py
=======================
Integration tests for UserRepository.

Uses the shared db_session fixture from conftest.py, which provides a
fresh AsyncSession per test pointed at statflow_test.

asyncio_mode = auto (set in pytest.ini) — no @pytest.mark.asyncio needed.

Important: The repository never commits. After create_user / update_user,
call `await db_session.flush()` (or `await db_session.commit()`) before
issuing queries that must see the written data.
"""

from __future__ import annotations

import uuid as _uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User, UserRole
from app.repositories.user_repository import UserRepository


# ---------------------------------------------------------------------------
# Helper utilities
# ---------------------------------------------------------------------------


def _unique_email() -> str:
    """Generate a unique email so tests never collide on the unique constraint."""
    return f"test-{_uuid.uuid4().hex[:8]}@example.com"


async def _make_user(
    repo: UserRepository,
    session: AsyncSession,
    *,
    email: str | None = None,
    hashed_password: str = "hashed_pw_placeholder",
    full_name: str | None = "Test User",
    role: UserRole = UserRole.VIEWER,
    is_active: bool = True,
) -> User:
    """Create a user and flush so it's visible within the session."""
    user = await repo.create_user(
        email=email or _unique_email(),
        hashed_password=hashed_password,
        full_name=full_name,
        role=role,
        is_active=is_active,
    )
    await session.flush()
    return user


# ---------------------------------------------------------------------------
# get_by_id
# ---------------------------------------------------------------------------


async def test_get_by_id_found(db_session: AsyncSession) -> None:
    repo = UserRepository(db_session)
    created = await _make_user(repo, db_session)

    found = await repo.get_by_id(created.id)

    assert found is not None
    assert found.id == created.id
    assert found.email == created.email


async def test_get_by_id_not_found(db_session: AsyncSession) -> None:
    repo = UserRepository(db_session)

    result = await repo.get_by_id(_uuid.uuid4())

    assert result is None


# ---------------------------------------------------------------------------
# get_by_email
# ---------------------------------------------------------------------------


async def test_get_by_email_case_insensitive(db_session: AsyncSession) -> None:
    repo = UserRepository(db_session)
    # Store with a lowercase email
    base = _unique_email()  # already lowercase
    await _make_user(repo, db_session, email=base)

    # Look up with UPPERCASE version
    found = await repo.get_by_email(base.upper())

    assert found is not None
    assert found.email == base


async def test_get_by_email_whitespace_normalized(db_session: AsyncSession) -> None:
    repo = UserRepository(db_session)
    base = _unique_email()
    await _make_user(repo, db_session, email=base)

    # Look up with surrounding whitespace
    found = await repo.get_by_email(f"  {base}  ")

    assert found is not None
    assert found.email == base


# ---------------------------------------------------------------------------
# create_user — email normalization
# ---------------------------------------------------------------------------


async def test_create_user_normalizes_email(db_session: AsyncSession) -> None:
    repo = UserRepository(db_session)

    user = await repo.create_user(
        email="  USER@Example.COM  ",
        hashed_password="some_hash",
        full_name="Norm Test",
        role=UserRole.ANALYST,
    )
    await db_session.flush()

    assert user.email == "user@example.com"


# ---------------------------------------------------------------------------
# list_users — ordering
# ---------------------------------------------------------------------------


async def test_list_users_ordering(db_session: AsyncSession) -> None:
    repo = UserRepository(db_session)

    # Create several users and flush each so created_at timestamps are set
    u1 = await _make_user(repo, db_session)
    u2 = await _make_user(repo, db_session)
    u3 = await _make_user(repo, db_session)

    users = await repo.list_users()

    # Filter to just the ones we created (the DB may have users from other tests)
    our_ids = {u1.id, u2.id, u3.id}
    our_users = [u for u in users if u.id in our_ids]

    assert len(our_users) == 3
    # Verify ascending created_at ordering is maintained
    for i in range(len(our_users) - 1):
        assert our_users[i].created_at <= our_users[i + 1].created_at


# ---------------------------------------------------------------------------
# email_exists
# ---------------------------------------------------------------------------


async def test_email_exists_true(db_session: AsyncSession) -> None:
    repo = UserRepository(db_session)
    user = await _make_user(repo, db_session)

    assert await repo.email_exists(user.email) is True


async def test_email_exists_false(db_session: AsyncSession) -> None:
    repo = UserRepository(db_session)

    assert await repo.email_exists("nobody@nowhere.example.com") is False


async def test_email_exists_excludes_user_id(db_session: AsyncSession) -> None:
    repo = UserRepository(db_session)
    user = await _make_user(repo, db_session)

    # When we exclude the user's own id, the email should not be considered taken
    result = await repo.email_exists(user.email, exclude_user_id=user.id)

    assert result is False


# ---------------------------------------------------------------------------
# update_user
# ---------------------------------------------------------------------------


async def test_update_email(db_session: AsyncSession) -> None:
    repo = UserRepository(db_session)
    user = await _make_user(repo, db_session, full_name="Alice")

    new_email = _unique_email()
    updated = await repo.update_user(user.id, email=f"  {new_email.upper()}  ")

    assert updated is not None
    assert updated.email == new_email  # normalized
    assert updated.full_name == "Alice"  # unchanged


async def test_update_role(db_session: AsyncSession) -> None:
    repo = UserRepository(db_session)
    user = await _make_user(repo, db_session, role=UserRole.VIEWER)

    updated = await repo.update_user(user.id, role=UserRole.ADMIN)

    assert updated is not None
    assert updated.role == UserRole.ADMIN
    assert updated.email == user.email  # unchanged


async def test_update_is_active(db_session: AsyncSession) -> None:
    repo = UserRepository(db_session)
    user = await _make_user(repo, db_session, is_active=True)

    updated = await repo.update_user(user.id, is_active=False)

    assert updated is not None
    assert updated.is_active is False


async def test_update_hashed_password(db_session: AsyncSession) -> None:
    repo = UserRepository(db_session)
    user = await _make_user(repo, db_session, hashed_password="old_hash")

    updated = await repo.update_user(user.id, hashed_password="new_hash")

    assert updated is not None
    assert updated.hashed_password == "new_hash"


async def test_update_only_supplied_fields(db_session: AsyncSession) -> None:
    repo = UserRepository(db_session)
    user = await _make_user(
        repo, db_session,
        full_name="Original Name",
        role=UserRole.VIEWER,
    )
    original_full_name = user.full_name

    # Only update the email; all other fields must stay the same
    new_email = _unique_email()
    updated = await repo.update_user(user.id, email=new_email)

    assert updated is not None
    assert updated.email == new_email
    assert updated.full_name == original_full_name  # untouched
    assert updated.role == UserRole.VIEWER  # untouched


# ---------------------------------------------------------------------------
# count_active_admins
# ---------------------------------------------------------------------------


async def test_count_active_admins_basic(db_session: AsyncSession) -> None:
    repo = UserRepository(db_session)

    # Capture baseline before creating new users
    baseline = await repo.count_active_admins()

    await _make_user(repo, db_session, role=UserRole.ADMIN, is_active=True)
    await _make_user(repo, db_session, role=UserRole.ADMIN, is_active=True)

    count = await repo.count_active_admins()

    assert count == baseline + 2


async def test_count_active_admins_excludes_inactive(db_session: AsyncSession) -> None:
    repo = UserRepository(db_session)

    baseline = await repo.count_active_admins()

    await _make_user(repo, db_session, role=UserRole.ADMIN, is_active=True)
    await _make_user(repo, db_session, role=UserRole.ADMIN, is_active=False)

    count = await repo.count_active_admins()

    assert count == baseline + 1  # only the active admin counted


async def test_count_active_admins_excludes_non_admin(db_session: AsyncSession) -> None:
    repo = UserRepository(db_session)

    baseline = await repo.count_active_admins()

    await _make_user(repo, db_session, role=UserRole.VIEWER, is_active=True)

    count = await repo.count_active_admins()

    assert count == baseline  # unchanged — VIEWER doesn't count
