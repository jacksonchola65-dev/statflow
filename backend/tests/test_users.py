"""
tests/test_users.py
===================
Integration tests for user management endpoints.

Covers REQ-13.5:
  REQ-13.5: Role enforcement — ADMIN can call user management endpoints;
            DATA_MANAGER returns 403 on user management; VIEWER returns 403
            on user management.

Also covers basic ADMIN CRUD success paths for the user management endpoints:
  POST   /api/v1/users
  GET    /api/v1/users
  GET    /api/v1/users/{id}
  PATCH  /api/v1/users/{id}
  DELETE /api/v1/users/{id}
"""

from __future__ import annotations

import sys

if sys.platform == "win32":
    import asyncio as _asyncio

    _asyncio.set_event_loop_policy(_asyncio.WindowsSelectorEventLoopPolicy())

import uuid

from app.core.config import settings
from app.core.security import create_access_token
from app.models.user import UserRole
from app.services.auth_service import AuthService

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _unique_email() -> str:
    return f"users-test-{uuid.uuid4().hex[:8]}@example.com"


async def _create_user(
    db_session,
    *,
    email: str | None = None,
    password: str = "correct horse battery staple",
    role: UserRole = UserRole.VIEWER,
    is_active: bool = True,
):
    """Create a user via AuthService and flush."""
    svc = AuthService(db_session)
    user = await svc.create_user(
        email=email or _unique_email(),
        password=password,
        full_name="Users Test User",
        role=role,
        is_active=is_active,
    )
    await db_session.flush()
    return user


def _cookie_for(user_id, role: UserRole) -> dict:
    """Return {cookie_name: token} for HTTP requests."""
    token = create_access_token(user_id=user_id, role=role)
    return {settings.AUTH_COOKIE_NAME: token}


def _with_csrf(base_cookies: dict | None = None) -> tuple[dict, dict]:
    """Return (cookies, headers) with CSRF token pair for state-mutating requests."""
    csrf_val = "test-csrf-token-fixed"
    cookies = dict(base_cookies or {})
    cookies[settings.CSRF_COOKIE_NAME] = csrf_val
    headers = {settings.CSRF_HEADER_NAME: csrf_val}
    return cookies, headers


# ---------------------------------------------------------------------------
# REQ-13.5 — Role enforcement: non-ADMIN roles get 403 on user endpoints
# ---------------------------------------------------------------------------


async def test_data_manager_get_users_returns_403(client, db_session):
    """DATA_MANAGER → GET /users returns 403 (REQ-13.5)."""
    user = await _create_user(db_session, role=UserRole.DATA_MANAGER)
    resp = await client.get("/api/v1/users", cookies=_cookie_for(user.id, user.role))
    assert resp.status_code == 403


async def test_analyst_get_users_returns_403(client, db_session):
    """ANALYST → GET /users returns 403 (REQ-13.5)."""
    user = await _create_user(db_session, role=UserRole.ANALYST)
    resp = await client.get("/api/v1/users", cookies=_cookie_for(user.id, user.role))
    assert resp.status_code == 403


async def test_viewer_get_users_returns_403(client, db_session):
    """VIEWER → GET /users returns 403 (REQ-13.5)."""
    user = await _create_user(db_session, role=UserRole.VIEWER)
    resp = await client.get("/api/v1/users", cookies=_cookie_for(user.id, user.role))
    assert resp.status_code == 403


async def test_unauthenticated_get_users_returns_401(client, db_session):
    """No auth cookie → GET /users returns 401 (REQ-3.1)."""
    resp = await client.get("/api/v1/users")
    assert resp.status_code == 401


async def test_data_manager_create_user_returns_403(client, db_session):
    """DATA_MANAGER → POST /users returns 403 (REQ-13.5)."""
    user = await _create_user(db_session, role=UserRole.DATA_MANAGER)
    cookies, headers = _with_csrf(_cookie_for(user.id, user.role))
    payload = {"email": _unique_email(), "password": "validpassword123"}
    resp = await client.post("/api/v1/users", json=payload, cookies=cookies, headers=headers)
    assert resp.status_code == 403


async def test_viewer_create_user_returns_403(client, db_session):
    """VIEWER → POST /users returns 403 (REQ-13.5)."""
    user = await _create_user(db_session, role=UserRole.VIEWER)
    cookies, headers = _with_csrf(_cookie_for(user.id, user.role))
    payload = {"email": _unique_email(), "password": "validpassword123"}
    resp = await client.post("/api/v1/users", json=payload, cookies=cookies, headers=headers)
    assert resp.status_code == 403


async def test_data_manager_patch_user_returns_403(client, db_session):
    """DATA_MANAGER → PATCH /users/{id} returns 403 (REQ-13.5)."""
    dm = await _create_user(db_session, role=UserRole.DATA_MANAGER)
    target = await _create_user(db_session, role=UserRole.VIEWER)
    cookies, headers = _with_csrf(_cookie_for(dm.id, dm.role))
    resp = await client.patch(
        f"/api/v1/users/{target.id}",
        json={"full_name": "Should Fail"},
        cookies=cookies,
        headers=headers,
    )
    assert resp.status_code == 403


async def test_viewer_delete_user_returns_403(client, db_session):
    """VIEWER → DELETE /users/{id} returns 403 (REQ-13.5)."""
    viewer = await _create_user(db_session, role=UserRole.VIEWER)
    target = await _create_user(db_session, role=UserRole.VIEWER)
    cookies, headers = _with_csrf(_cookie_for(viewer.id, viewer.role))
    resp = await client.delete(
        f"/api/v1/users/{target.id}",
        cookies=cookies,
        headers=headers,
    )
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# ADMIN CRUD success paths
# ---------------------------------------------------------------------------


async def test_admin_can_list_users(client, db_session):
    """ADMIN → GET /users returns 200 with list and total (REQ-13.5 / REQ-8.2)."""
    admin = await _create_user(db_session, role=UserRole.ADMIN)
    resp = await client.get("/api/v1/users", cookies=_cookie_for(admin.id, admin.role))
    assert resp.status_code == 200
    data = resp.json()
    assert "users" in data
    assert isinstance(data["users"], list)
    assert "total" in data


async def test_admin_can_get_user_by_id(client, db_session):
    """ADMIN → GET /users/{id} returns 200 with the correct user (REQ-8.3)."""
    admin = await _create_user(db_session, role=UserRole.ADMIN)
    target = await _create_user(db_session, role=UserRole.VIEWER)
    resp = await client.get(
        f"/api/v1/users/{target.id}",
        cookies=_cookie_for(admin.id, admin.role),
    )
    assert resp.status_code == 200
    assert resp.json()["id"] == str(target.id)
    assert resp.json()["email"] == target.email


async def test_admin_can_create_user(client, db_session):
    """ADMIN → POST /users with valid body returns 201 with new user (REQ-8.1)."""
    admin = await _create_user(db_session, role=UserRole.ADMIN)
    cookies, headers = _with_csrf(_cookie_for(admin.id, admin.role))
    email = _unique_email()
    payload = {
        "email": email,
        "password": "validpassword123",
        "full_name": "New User",
        "role": "VIEWER",
    }
    resp = await client.post("/api/v1/users", json=payload, cookies=cookies, headers=headers)
    assert resp.status_code == 201
    data = resp.json()
    assert data["email"] == email
    assert data["role"] == "VIEWER"
    assert "hashed_password" not in data


async def test_admin_can_update_user(client, db_session):
    """ADMIN → PATCH /users/{id} returns 200 with updated fields (REQ-8.4)."""
    admin = await _create_user(db_session, role=UserRole.ADMIN)
    target = await _create_user(db_session, role=UserRole.VIEWER)
    cookies, headers = _with_csrf(_cookie_for(admin.id, admin.role))
    resp = await client.patch(
        f"/api/v1/users/{target.id}",
        json={"full_name": "Updated Name", "role": "ANALYST"},
        cookies=cookies,
        headers=headers,
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["full_name"] == "Updated Name"
    assert data["role"] == "ANALYST"


async def test_admin_can_soft_delete_user(client, db_session):
    """ADMIN → DELETE /users/{id} returns 204; user is_active becomes False (REQ-8.5)."""
    admin = await _create_user(db_session, role=UserRole.ADMIN)
    # Second admin so first admin isn't "last admin"
    await _create_user(db_session, role=UserRole.ADMIN)
    target = await _create_user(db_session, role=UserRole.VIEWER)
    cookies, headers = _with_csrf(_cookie_for(admin.id, admin.role))

    del_resp = await client.delete(
        f"/api/v1/users/{target.id}",
        cookies=cookies,
        headers=headers,
    )
    assert del_resp.status_code == 204

    # Confirm user is still retrievable but marked inactive (soft delete)
    get_resp = await client.get(
        f"/api/v1/users/{target.id}",
        cookies=_cookie_for(admin.id, admin.role),
    )
    assert get_resp.status_code == 200
    assert get_resp.json()["is_active"] is False


async def test_get_nonexistent_user_returns_404(client, db_session):
    """ADMIN → GET /users/{id} for unknown UUID returns 404."""
    admin = await _create_user(db_session, role=UserRole.ADMIN)
    resp = await client.get(
        f"/api/v1/users/{uuid.uuid4()}",
        cookies=_cookie_for(admin.id, admin.role),
    )
    assert resp.status_code == 404


async def test_create_duplicate_email_returns_409(client, db_session):
    """ADMIN creating a user with duplicate email → 409."""
    admin = await _create_user(db_session, role=UserRole.ADMIN)
    cookies, headers = _with_csrf(_cookie_for(admin.id, admin.role))
    email = _unique_email()
    payload = {"email": email, "password": "validpassword123"}

    resp1 = await client.post("/api/v1/users", json=payload, cookies=cookies, headers=headers)
    assert resp1.status_code == 201

    resp2 = await client.post("/api/v1/users", json=payload, cookies=cookies, headers=headers)
    assert resp2.status_code == 409


async def test_response_never_contains_hashed_password(client, db_session):
    """User management responses must never expose hashed_password (REQ-1.3)."""
    admin = await _create_user(db_session, role=UserRole.ADMIN)
    cookies, headers = _with_csrf(_cookie_for(admin.id, admin.role))
    payload = {"email": _unique_email(), "password": "validpassword123"}

    create_resp = await client.post("/api/v1/users", json=payload, cookies=cookies, headers=headers)
    assert create_resp.status_code == 201
    assert "hashed_password" not in create_resp.text

    list_resp = await client.get("/api/v1/users", cookies=_cookie_for(admin.id, admin.role))
    assert list_resp.status_code == 200
    assert "hashed_password" not in list_resp.text


# ---------------------------------------------------------------------------
# REQ-13.5 — ADMIN seed fixture usage (admin_user from conftest)
# ---------------------------------------------------------------------------


async def test_admin_user_fixture_can_access_users(client, admin_user):
    """The seeded admin_user fixture has ADMIN role and can access /users."""
    resp = await client.get(
        "/api/v1/users",
        cookies=_cookie_for(admin_user.id, admin_user.role),
    )
    assert resp.status_code == 200


async def test_admin_user_fixture_role_is_admin(admin_user):
    """The seeded admin_user fixture must have ADMIN role."""
    assert admin_user.role == UserRole.ADMIN
    assert admin_user.is_active is True
