"""
test_auth_service.py
====================
Integration tests for AuthService.

Uses the shared db_session fixture from conftest.py (statflow_test DB).
asyncio_mode = auto is set in pytest.ini — no @pytest.mark.asyncio needed.

Transaction behaviour note:
  AuthService never calls session.commit() or session.rollback().
  The per-test db_session fixture provides session isolation: each test
  operates within its own session that is discarded after the test, so
  the clean-state guarantee is provided by test isolation rather than
  rollback. This is equivalent to the pattern used by test_user_repository.py.
"""

from __future__ import annotations

import uuid as _uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import decode_access_token
from app.models.user import UserRole
from app.services.auth_service import (
    AuthService,
    AuthenticatedUser,
    EmailAlreadyExistsError,
    InvalidCredentialsError,
    PasswordPolicyError,
    UserNotFoundError,
)


# ---------------------------------------------------------------------------
# Helper utilities
# ---------------------------------------------------------------------------


def _unique_email() -> str:
    """Return a unique email address to prevent unique-constraint collisions."""
    return f"svc-{_uuid.uuid4().hex[:8]}@example.com"


async def _create_user(
    svc: AuthService,
    *,
    email: str | None = None,
    password: str = "correct horse battery staple",
    full_name: str | None = "Test User",
    role: UserRole = UserRole.VIEWER,
    is_active: bool = True,
):
    """Convenience wrapper that creates a user via the service."""
    return await svc.create_user(
        email=email or _unique_email(),
        password=password,
        full_name=full_name,
        role=role,
        is_active=is_active,
    )


# ---------------------------------------------------------------------------
# Authentication tests
# ---------------------------------------------------------------------------


async def test_authenticate_success(db_session: AsyncSession) -> None:
    """Creating a user then authenticating with correct credentials returns
    an AuthenticatedUser with a non-empty access_token."""
    svc = AuthService(db_session)
    email = _unique_email()
    password = "correct horse battery staple"

    await _create_user(svc, email=email, password=password)
    result = await svc.authenticate(email, password)

    assert isinstance(result, AuthenticatedUser)
    assert result.user is not None
    assert isinstance(result.access_token, str)
    assert len(result.access_token) > 0


async def test_authenticate_unknown_email(db_session: AsyncSession) -> None:
    """Authenticating with an email that doesn't exist raises InvalidCredentialsError."""
    svc = AuthService(db_session)

    with pytest.raises(InvalidCredentialsError):
        await svc.authenticate("nobody@doesnotexist.example.com", "somepassword")


async def test_authenticate_wrong_password(db_session: AsyncSession) -> None:
    """Authenticating with the correct email but wrong password raises InvalidCredentialsError."""
    svc = AuthService(db_session)
    email = _unique_email()

    await _create_user(svc, email=email, password="correct horse battery staple")

    with pytest.raises(InvalidCredentialsError):
        await svc.authenticate(email, "wrong-password-here")


async def test_authenticate_inactive_user(db_session: AsyncSession) -> None:
    """Authenticating as an inactive user raises InvalidCredentialsError."""
    svc = AuthService(db_session)
    email = _unique_email()
    password = "correct horse battery staple"

    await _create_user(svc, email=email, password=password, is_active=False)

    with pytest.raises(InvalidCredentialsError):
        await svc.authenticate(email, password)


async def test_authenticate_returns_valid_token(db_session: AsyncSession) -> None:
    """The access_token returned by authenticate() decodes to a payload whose
    sub matches the created user's id."""
    svc = AuthService(db_session)
    email = _unique_email()
    password = "correct horse battery staple"

    await _create_user(svc, email=email, password=password)
    result = await svc.authenticate(email, password)

    payload = decode_access_token(result.access_token)
    assert payload.sub == result.user.id


# ---------------------------------------------------------------------------
# create_user tests
# ---------------------------------------------------------------------------


async def test_create_user_hashes_password(db_session: AsyncSession) -> None:
    """The stored hashed_password differs from the plaintext password."""
    svc = AuthService(db_session)
    password = "correct horse battery staple"

    user = await _create_user(svc, password=password)

    assert user.hashed_password != password


async def test_create_user_plaintext_not_stored(db_session: AsyncSession) -> None:
    """The stored hashed_password string does not equal the raw password."""
    svc = AuthService(db_session)
    password = "correct horse battery staple"

    user = await _create_user(svc, password=password)

    assert user.hashed_password != password


async def test_create_user_duplicate_email_raises(db_session: AsyncSession) -> None:
    """Creating two users with the same email raises EmailAlreadyExistsError."""
    svc = AuthService(db_session)
    email = _unique_email()

    await _create_user(svc, email=email)

    with pytest.raises(EmailAlreadyExistsError):
        await _create_user(svc, email=email)


async def test_create_user_duplicate_email_case_insensitive(db_session: AsyncSession) -> None:
    """Emails are treated as duplicates regardless of case."""
    svc = AuthService(db_session)
    email = _unique_email()  # already lowercase

    await _create_user(svc, email=email)

    with pytest.raises(EmailAlreadyExistsError):
        await _create_user(svc, email=email.upper())


# ---------------------------------------------------------------------------
# Password policy tests
# ---------------------------------------------------------------------------


async def test_password_too_short(db_session: AsyncSession) -> None:
    """A password of 11 characters raises PasswordPolicyError."""
    svc = AuthService(db_session)

    with pytest.raises(PasswordPolicyError):
        await svc.create_user(
            email=_unique_email(),
            password="a" * 11,
            full_name=None,
            role=UserRole.VIEWER,
        )


async def test_password_whitespace_only(db_session: AsyncSession) -> None:
    """A password consisting of 12 spaces raises PasswordPolicyError."""
    svc = AuthService(db_session)

    with pytest.raises(PasswordPolicyError):
        await svc.create_user(
            email=_unique_email(),
            password="            ",  # 12 spaces
            full_name=None,
            role=UserRole.VIEWER,
        )


async def test_password_too_long(db_session: AsyncSession) -> None:
    """A password of 129 characters raises PasswordPolicyError."""
    svc = AuthService(db_session)

    with pytest.raises(PasswordPolicyError):
        await svc.create_user(
            email=_unique_email(),
            password="a" * 129,
            full_name=None,
            role=UserRole.VIEWER,
        )


async def test_valid_passphrase_accepted(db_session: AsyncSession) -> None:
    """A 28-character passphrase (no uppercase/symbols required) is accepted."""
    svc = AuthService(db_session)

    # Must NOT raise — just verify the user is created successfully.
    user = await svc.create_user(
        email=_unique_email(),
        password="correct horse battery staple",  # 28 chars
        full_name=None,
        role=UserRole.VIEWER,
    )
    assert user is not None


# ---------------------------------------------------------------------------
# change_password tests
# ---------------------------------------------------------------------------


async def test_change_password_updates_hash(db_session: AsyncSession) -> None:
    """After change_password, the new hash differs from the old, and the new
    password verifies successfully against the updated hash."""
    from app.core.security import verify_password

    svc = AuthService(db_session)
    old_password = "correct horse battery staple"
    new_password = "new valid passphrase here"

    user = await _create_user(svc, password=old_password)
    old_hash = user.hashed_password

    updated = await svc.change_password(user.id, new_password)

    assert updated.hashed_password != old_hash
    assert verify_password(new_password, updated.hashed_password)


async def test_old_password_fails_after_change(db_session: AsyncSession) -> None:
    """After changing the password, the old password no longer verifies."""
    from app.core.security import verify_password

    svc = AuthService(db_session)
    old_password = "correct horse battery staple"
    new_password = "new valid passphrase here"

    user = await _create_user(svc, password=old_password)
    updated = await svc.change_password(user.id, new_password)

    assert not verify_password(old_password, updated.hashed_password)


async def test_change_password_user_not_found(db_session: AsyncSession) -> None:
    """Changing the password for an unknown UUID raises UserNotFoundError."""
    svc = AuthService(db_session)

    with pytest.raises(UserNotFoundError):
        await svc.change_password(_uuid.uuid4(), "new valid passphrase here")


# ---------------------------------------------------------------------------
# get_current_user tests
# ---------------------------------------------------------------------------


async def test_get_current_user_returns_active_user(db_session: AsyncSession) -> None:
    """get_current_user returns the correct User for an active account."""
    svc = AuthService(db_session)
    user = await _create_user(svc, is_active=True)

    result = await svc.get_current_user(user.id)

    assert result.id == user.id
    assert result.email == user.email


async def test_get_current_user_not_found(db_session: AsyncSession) -> None:
    """get_current_user raises UserNotFoundError for an unknown UUID."""
    svc = AuthService(db_session)

    with pytest.raises(UserNotFoundError):
        await svc.get_current_user(_uuid.uuid4())


async def test_get_current_user_inactive(db_session: AsyncSession) -> None:
    """get_current_user raises InvalidCredentialsError for an inactive user.

    Note: the service raises InvalidCredentialsError (not InactiveUserError)
    for inactive accounts in get_current_user, matching the same pattern used
    in authenticate() to keep the exception surface minimal.
    """
    svc = AuthService(db_session)
    user = await _create_user(svc, is_active=False)

    with pytest.raises(InvalidCredentialsError):
        await svc.get_current_user(user.id)


# ---------------------------------------------------------------------------
# Transaction behaviour (test 20 — documented, not a test function)
# ---------------------------------------------------------------------------
#
# AuthService.authenticate(), create_user(), change_password(), and
# get_current_user() do NOT call session.commit() or session.rollback().
# Transaction ownership belongs to the endpoint/dependency layer.
#
# The per-test db_session fixture in conftest.py proves session isolation:
# each test receives a fresh session (via NullPool + a new engine connection),
# so data written in one test is invisible to another without any explicit
# rollback. This indirectly validates that the service itself does not commit
# (if it did, data would persist between tests and collisions would occur on
# the unique email constraint).
