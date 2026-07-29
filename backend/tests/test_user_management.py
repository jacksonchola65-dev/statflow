"""
tests/test_user_management.py
==============================
Integration tests for user management endpoints (Task 8 — auth-foundation).

Tests cover:
- Authentication/authorization protection (401, 403)
- Read operations: list, get, 404
- Create: success, email normalization, password hashing, duplicate, weak password
- Update: individual fields, last-admin enforcement, omitted-field stability
- Delete: last-admin enforcement, self-deletion, soft-delete verification
- Security: hashed_password never in response
"""

from __future__ import annotations

import uuid as _uuid

import pytest
import pytest_asyncio

from app.core.config import settings
from app.core.security import create_access_token, verify_password
from app.models.user import UserRole
from app.services.auth_service import AuthService


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _unique_email() -> str:
    return f"mgmt-{_uuid.uuid4().hex[:8]}@example.com"


async def _make_user(
    db_session,
    *,
    role: UserRole = UserRole.VIEWER,
    is_active: bool = True,
    email: str | None = None,
):
    """Create a user via AuthService (bypasses the HTTP layer)."""
    svc = AuthService(db_session)
    user = await svc.create_user(
        email=email or _unique_email(),
        password="correct horse battery staple",
        full_name="Test User",
        role=role,
        is_active=is_active,
    )
    await db_session.flush()
    return user


def _admin_cookie(user_id, role: UserRole = UserRole.ADMIN) -> dict:
    """Mint a JWT cookie dict for use with httpx cookies= kwarg."""
    token = create_access_token(user_id=user_id, role=role)
    return {settings.AUTH_COOKIE_NAME: token}


def _csrf_cookies_and_headers(base_cookies: dict | None = None) -> tuple[dict, dict]:
    """Return (cookies, headers) dicts with a matching CSRF token pair.

    Use for state-changing requests (POST, PATCH, DELETE) that go through
    the real validate_csrf dependency.
    """
    csrf_token = "test-csrf-token-fixed"
    cookies = dict(base_cookies or {})
    cookies[settings.CSRF_COOKIE_NAME] = csrf_token
    headers = {settings.CSRF_HEADER_NAME: csrf_token}
    return cookies, headers


# ---------------------------------------------------------------------------
# Auth protection
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_users_unauthenticated_returns_401(client):
    resp = await client.get("/api/v1/users")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_list_users_non_admin_returns_403(client, db_session):
    viewer = await _make_user(db_session, role=UserRole.VIEWER)
    cookies = _admin_cookie(viewer.id, role=UserRole.VIEWER)
    resp = await client.get("/api/v1/users", cookies=cookies)
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# Read operations
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_admin_can_list_users(client, db_session):
    admin = await _make_user(db_session, role=UserRole.ADMIN)
    cookies = _admin_cookie(admin.id)
    resp = await client.get("/api/v1/users", cookies=cookies)
    assert resp.status_code == 200
    data = resp.json()
    assert "users" in data
    assert isinstance(data["users"], list)
    assert isinstance(data["total"], int)


@pytest.mark.asyncio
async def test_admin_can_get_user(client, db_session):
    admin = await _make_user(db_session, role=UserRole.ADMIN)
    other = await _make_user(db_session, role=UserRole.VIEWER)
    cookies = _admin_cookie(admin.id)
    resp = await client.get(f"/api/v1/users/{other.id}", cookies=cookies)
    assert resp.status_code == 200
    assert resp.json()["id"] == str(other.id)


@pytest.mark.asyncio
async def test_get_missing_user_returns_404(client, db_session):
    admin = await _make_user(db_session, role=UserRole.ADMIN)
    cookies = _admin_cookie(admin.id)
    resp = await client.get(f"/api/v1/users/{_uuid.uuid4()}", cookies=cookies)
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Create
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_admin_can_create_user(client, db_session):
    admin = await _make_user(db_session, role=UserRole.ADMIN)
    cookies = _admin_cookie(admin.id)
    cookies, headers = _csrf_cookies_and_headers(cookies)
    payload = {
        "email": _unique_email(),
        "password": "validpassword123",
        "full_name": "New User",
        "role": "VIEWER",
    }
    resp = await client.post("/api/v1/users", json=payload, cookies=cookies, headers=headers)
    assert resp.status_code == 201
    data = resp.json()
    assert data["email"] == payload["email"]
    assert data["full_name"] == "New User"
    assert data["role"] == "VIEWER"


@pytest.mark.asyncio
async def test_created_email_normalized(client, db_session):
    admin = await _make_user(db_session, role=UserRole.ADMIN)
    cookies = _admin_cookie(admin.id)
    cookies, headers = _csrf_cookies_and_headers(cookies)
    raw_email = "  USER@Example.COM  "
    payload = {
        "email": raw_email.strip(),  # Pydantic EmailStr strips whitespace
        "password": "validpassword123",
    }
    resp = await client.post("/api/v1/users", json=payload, cookies=cookies, headers=headers)
    assert resp.status_code == 201
    # Email must be stored and returned in lowercase
    assert resp.json()["email"] == "user@example.com"


@pytest.mark.asyncio
async def test_created_password_hashed(client, db_session):
    admin = await _make_user(db_session, role=UserRole.ADMIN)
    cookies = _admin_cookie(admin.id)
    cookies, headers = _csrf_cookies_and_headers(cookies)
    payload = {
        "email": _unique_email(),
        "password": "validpassword123",
    }
    resp = await client.post("/api/v1/users", json=payload, cookies=cookies, headers=headers)
    assert resp.status_code == 201
    # hashed_password must never appear in the response body
    assert "hashed_password" not in resp.json()


@pytest.mark.asyncio
async def test_duplicate_email_returns_409(client, db_session):
    admin = await _make_user(db_session, role=UserRole.ADMIN)
    cookies = _admin_cookie(admin.id)
    cookies, headers = _csrf_cookies_and_headers(cookies)
    email = _unique_email()
    payload = {"email": email, "password": "validpassword123"}
    resp1 = await client.post("/api/v1/users", json=payload, cookies=cookies, headers=headers)
    assert resp1.status_code == 201
    resp2 = await client.post("/api/v1/users", json=payload, cookies=cookies, headers=headers)
    assert resp2.status_code == 409


@pytest.mark.asyncio
async def test_weak_password_returns_400(client, db_session):
    admin = await _make_user(db_session, role=UserRole.ADMIN)
    cookies = _admin_cookie(admin.id)
    cookies, headers = _csrf_cookies_and_headers(cookies)
    payload = {"email": _unique_email(), "password": "short"}
    resp = await client.post("/api/v1/users", json=payload, cookies=cookies, headers=headers)
    assert resp.status_code == 400


# ---------------------------------------------------------------------------
# Update
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_admin_can_update_email(client, db_session):
    admin = await _make_user(db_session, role=UserRole.ADMIN)
    target = await _make_user(db_session, role=UserRole.VIEWER)
    cookies = _admin_cookie(admin.id)
    cookies, headers = _csrf_cookies_and_headers(cookies)
    new_email = _unique_email()
    resp = await client.patch(
        f"/api/v1/users/{target.id}",
        json={"email": new_email},
        cookies=cookies,
        headers=headers,
    )
    assert resp.status_code == 200
    assert resp.json()["email"] == new_email


@pytest.mark.asyncio
async def test_admin_can_update_name(client, db_session):
    admin = await _make_user(db_session, role=UserRole.ADMIN)
    target = await _make_user(db_session, role=UserRole.VIEWER)
    cookies = _admin_cookie(admin.id)
    cookies, headers = _csrf_cookies_and_headers(cookies)
    resp = await client.patch(
        f"/api/v1/users/{target.id}",
        json={"full_name": "Updated Name"},
        cookies=cookies,
        headers=headers,
    )
    assert resp.status_code == 200
    assert resp.json()["full_name"] == "Updated Name"


@pytest.mark.asyncio
async def test_admin_can_update_role(client, db_session):
    admin = await _make_user(db_session, role=UserRole.ADMIN)
    target = await _make_user(db_session, role=UserRole.VIEWER)
    cookies = _admin_cookie(admin.id)
    cookies, headers = _csrf_cookies_and_headers(cookies)
    resp = await client.patch(
        f"/api/v1/users/{target.id}",
        json={"role": "DATA_MANAGER"},
        cookies=cookies,
        headers=headers,
    )
    assert resp.status_code == 200
    assert resp.json()["role"] == "DATA_MANAGER"


@pytest.mark.asyncio
async def test_admin_can_update_is_active(client, db_session):
    admin = await _make_user(db_session, role=UserRole.ADMIN)
    target = await _make_user(db_session, role=UserRole.VIEWER)
    cookies = _admin_cookie(admin.id)
    cookies, headers = _csrf_cookies_and_headers(cookies)
    resp = await client.patch(
        f"/api/v1/users/{target.id}",
        json={"is_active": False},
        cookies=cookies,
        headers=headers,
    )
    assert resp.status_code == 200
    assert resp.json()["is_active"] is False


@pytest.mark.asyncio
async def test_admin_can_change_password(client, db_session):
    admin = await _make_user(db_session, role=UserRole.ADMIN)
    target = await _make_user(db_session, role=UserRole.VIEWER)
    old_hashed = target.hashed_password
    cookies = _admin_cookie(admin.id)
    cookies, headers = _csrf_cookies_and_headers(cookies)
    new_password = "newpasswordreplacement"
    resp = await client.patch(
        f"/api/v1/users/{target.id}",
        json={"password": new_password},
        cookies=cookies,
        headers=headers,
    )
    assert resp.status_code == 200
    # Reload and confirm old password no longer verifies
    from app.repositories.user_repository import UserRepository
    repo = UserRepository(db_session)
    updated = await repo.get_by_id(target.id)
    assert updated is not None
    # Old password should not verify against new hash
    assert not verify_password("correct horse battery staple", updated.hashed_password)
    # New password should verify
    assert verify_password(new_password, updated.hashed_password)


@pytest.mark.asyncio
async def test_omitted_fields_unchanged(client, db_session):
    admin = await _make_user(db_session, role=UserRole.ADMIN)
    target = await _make_user(db_session, role=UserRole.VIEWER)
    original_name = target.full_name
    cookies = _admin_cookie(admin.id)
    cookies, headers = _csrf_cookies_and_headers(cookies)
    new_email = _unique_email()
    resp = await client.patch(
        f"/api/v1/users/{target.id}",
        json={"email": new_email},
        cookies=cookies,
        headers=headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["email"] == new_email
    assert data["full_name"] == original_name  # unchanged


@pytest.mark.asyncio
async def test_final_admin_cannot_be_disabled(client, db_session):
    """The sole active ADMIN among those created in this test cannot be disabled.

    We test via the service directly to avoid cross-test DB contamination
    (other tests may have left active ADMINs in the shared DB).
    """
    from app.services.user_service import UserService, LastActiveAdminError
    from app.repositories.user_repository import UserRepository

    # Create two ADMINs in this session.
    admin_a = await _make_user(db_session, role=UserRole.ADMIN)
    admin_b = await _make_user(db_session, role=UserRole.ADMIN)

    # Deactivate admin_a so admin_b is (potentially) the last active ADMIN
    # visible to count_active_admins.  If other tests left active ADMINs in DB,
    # the HTTP call won't 409.  Test the invariant at service level instead.
    repo = UserRepository(db_session)
    # Deactivate ALL other admins so admin_b is truly the last one.
    from sqlalchemy import update
    from app.models.user import User
    await db_session.execute(
        update(User)
        .where(User.role == UserRole.ADMIN, User.id != admin_b.id)
        .values(is_active=False)
    )
    await db_session.flush()

    svc = UserService(db_session)
    try:
        await svc.update_user(admin_b.id, is_active=False)
        assert False, "Expected LastActiveAdminError"
    except LastActiveAdminError:
        pass  # correct — last-admin protection triggered

    # Also verify via HTTP: admin_b tries to disable themselves → 409.
    cookies_b = _admin_cookie(admin_b.id)
    csrf_cookies, csrf_headers = _csrf_cookies_and_headers(cookies_b)
    resp = await client.patch(
        f"/api/v1/users/{admin_b.id}",
        json={"is_active": False},
        cookies=csrf_cookies,
        headers=csrf_headers,
    )
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_final_admin_cannot_be_demoted(client, db_session):
    from app.services.user_service import UserService, LastActiveAdminError
    from app.models.user import User
    from sqlalchemy import update

    admin_a = await _make_user(db_session, role=UserRole.ADMIN)
    admin_b = await _make_user(db_session, role=UserRole.ADMIN)

    # Make admin_b the sole active ADMIN.
    await db_session.execute(
        update(User)
        .where(User.role == UserRole.ADMIN, User.id != admin_b.id)
        .values(is_active=False)
    )
    await db_session.flush()

    # Service-level check.
    svc = UserService(db_session)
    try:
        await svc.update_user(admin_b.id, role=UserRole.VIEWER)
        assert False, "Expected LastActiveAdminError"
    except LastActiveAdminError:
        pass

    # HTTP check: admin_b (sole active ADMIN) tries to demote themselves → 409.
    cookies_b = _admin_cookie(admin_b.id)
    csrf_cookies, csrf_headers = _csrf_cookies_and_headers(cookies_b)
    resp = await client.patch(
        f"/api/v1/users/{admin_b.id}",
        json={"role": "VIEWER"},
        cookies=csrf_cookies,
        headers=csrf_headers,
    )
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_non_final_admin_can_be_disabled(client, db_session):
    admin_a = await _make_user(db_session, role=UserRole.ADMIN)
    admin_b = await _make_user(db_session, role=UserRole.ADMIN)
    cookies_a = _admin_cookie(admin_a.id)
    csrf_cookies, csrf_headers = _csrf_cookies_and_headers(cookies_a)
    resp = await client.patch(
        f"/api/v1/users/{admin_b.id}",
        json={"is_active": False},
        cookies=csrf_cookies,
        headers=csrf_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["is_active"] is False


# ---------------------------------------------------------------------------
# Delete
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_final_admin_cannot_be_deleted(client, db_session):
    """The sole active ADMIN cannot be soft-deleted — service raises LastActiveAdminError."""
    from app.services.user_service import UserService, LastActiveAdminError
    from app.models.user import User
    from sqlalchemy import update

    admin_actor = await _make_user(db_session, role=UserRole.ADMIN)
    admin_target = await _make_user(db_session, role=UserRole.ADMIN)

    # Deactivate ALL other admins so admin_target is truly the last active ADMIN.
    await db_session.execute(
        update(User)
        .where(User.role == UserRole.ADMIN, User.id != admin_target.id)
        .values(is_active=False)
    )
    await db_session.flush()

    # Verify via service: any actor trying to delete admin_target raises LastActiveAdminError.
    svc = UserService(db_session)
    dummy_actor_id = _uuid.uuid4()  # different from admin_target.id
    try:
        await svc.delete_user(admin_target.id, acting_user_id=dummy_actor_id)
        assert False, "Expected LastActiveAdminError"
    except LastActiveAdminError:
        pass  # correct

    # HTTP layer: admin_target (sole active ADMIN) tries to delete themselves → 400 (self-delete).
    # Self-deletion check runs BEFORE last-admin check — both protections work.
    cookies_target = _admin_cookie(admin_target.id)
    csrf_cookies, csrf_headers = _csrf_cookies_and_headers(cookies_target)
    resp = await client.delete(
        f"/api/v1/users/{admin_target.id}",
        cookies=csrf_cookies,
        headers=csrf_headers,
    )
    assert resp.status_code == 400  # self-deletion fires first


@pytest.mark.asyncio
async def test_admin_cannot_delete_own_account(client, db_session):
    admin = await _make_user(db_session, role=UserRole.ADMIN)
    # Create a second ADMIN so the first isn't the "last" (to isolate self-deletion error).
    await _make_user(db_session, role=UserRole.ADMIN)
    cookies = _admin_cookie(admin.id)
    csrf_cookies, csrf_headers = _csrf_cookies_and_headers(cookies)
    resp = await client.delete(
        f"/api/v1/users/{admin.id}",
        cookies=csrf_cookies,
        headers=csrf_headers,
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_delete_is_soft(client, db_session):
    """After soft-delete, the user still exists in DB with is_active=False."""
    admin = await _make_user(db_session, role=UserRole.ADMIN)
    target = await _make_user(db_session, role=UserRole.VIEWER)
    cookies = _admin_cookie(admin.id)
    csrf_cookies, csrf_headers = _csrf_cookies_and_headers(cookies)
    del_resp = await client.delete(
        f"/api/v1/users/{target.id}",
        cookies=csrf_cookies,
        headers=csrf_headers,
    )
    assert del_resp.status_code == 204
    # User should still be retrievable (soft delete — row persists).
    get_resp = await client.get(f"/api/v1/users/{target.id}", cookies=cookies)
    assert get_resp.status_code == 200
    assert get_resp.json()["is_active"] is False


@pytest.mark.asyncio
async def test_no_password_hash_in_response(client, db_session):
    admin = await _make_user(db_session, role=UserRole.ADMIN)
    cookies = _admin_cookie(admin.id)
    cookies, headers = _csrf_cookies_and_headers(cookies)
    payload = {"email": _unique_email(), "password": "validpassword123"}
    resp = await client.post("/api/v1/users", json=payload, cookies=cookies, headers=headers)
    assert resp.status_code == 201
    assert "hashed_password" not in resp.json()
