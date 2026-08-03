"""
tests/test_auth_endpoints.py
============================
Endpoint tests for POST /api/v1/auth/login, GET /api/v1/auth/me,
and POST /api/v1/auth/logout.

Fixture dependencies (from conftest.py):
- client      — AsyncClient wired to the test DB
- db_session  — AsyncSession for the test DB
"""

from __future__ import annotations

import uuid as _uuid

import pytest
from app.core.config import settings
from app.models.user import UserRole

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _unique_email() -> str:
    return f"ep-{_uuid.uuid4().hex[:8]}@example.com"


async def _register(
    db_session,
    email: str | None = None,
    password: str = "correct horse battery staple",
    role: UserRole = UserRole.VIEWER,
    is_active: bool = True,
):
    """Create a user via AuthService and flush (no commit)."""
    from app.services.auth_service import AuthService

    svc = AuthService(db_session)
    user = await svc.create_user(
        email=email or _unique_email(),
        password=password,
        full_name="Endpoint Test User",
        role=role,
        is_active=is_active,
    )
    await db_session.flush()
    return user


def _get_set_cookie_header(response, name: str) -> str | None:
    """Return the raw Set-Cookie header value for the named cookie."""
    for header_name, header_value in response.headers.multi_items():
        if header_name.lower() == "set-cookie" and f"{name}=" in header_value:
            return header_value
    return None


# ---------------------------------------------------------------------------
# Login tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_login_success_returns_user_and_expiry(client, db_session):
    """POST /login with valid creds → 200, user.id, expires_in > 0, csrf_token."""
    user = await _register(db_session)
    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": user.email, "password": "correct horse battery staple"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "user" in body
    assert str(user.id) == body["user"]["id"]
    assert body["expires_in"] > 0
    assert body["csrf_token"]


@pytest.mark.asyncio
async def test_login_sets_httponly_auth_cookie(client, db_session):
    """POST /login → auth cookie is present and marked HttpOnly."""
    user = await _register(db_session)
    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": user.email, "password": "correct horse battery staple"},
    )
    assert resp.status_code == 200
    raw = _get_set_cookie_header(resp, settings.AUTH_COOKIE_NAME)
    assert raw is not None, "Auth cookie not found in Set-Cookie headers"
    assert "httponly" in raw.lower()


@pytest.mark.asyncio
async def test_login_auth_cookie_attributes(client, db_session):
    """POST /login → auth cookie has path=/, max_age > 0, samesite matches settings."""
    user = await _register(db_session)
    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": user.email, "password": "correct horse battery staple"},
    )
    assert resp.status_code == 200
    raw = _get_set_cookie_header(resp, settings.AUTH_COOKIE_NAME)
    assert raw is not None
    assert "path=/" in raw.lower()
    assert "max-age=" in raw.lower()
    # Confirm max_age value is positive
    for part in raw.split(";"):
        part = part.strip()
        if part.lower().startswith("max-age="):
            assert int(part.split("=", 1)[1]) > 0
    assert settings.COOKIE_SAMESITE.lower() in raw.lower()


@pytest.mark.asyncio
async def test_login_does_not_return_jwt_in_body(client, db_session):
    """POST /login → JSON body must NOT contain access_token or token keys."""
    user = await _register(db_session)
    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": user.email, "password": "correct horse battery staple"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "access_token" not in body
    assert "token" not in body


@pytest.mark.asyncio
async def test_login_issues_csrf_cookie(client, db_session):
    """POST /login → CSRF cookie is present and NOT HttpOnly."""
    user = await _register(db_session)
    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": user.email, "password": "correct horse battery staple"},
    )
    assert resp.status_code == 200
    raw = _get_set_cookie_header(resp, settings.CSRF_COOKIE_NAME)
    assert raw is not None, "CSRF cookie not found in Set-Cookie headers"
    assert "httponly" not in raw.lower()


@pytest.mark.asyncio
async def test_login_unknown_email_returns_401(client, db_session):
    """POST /login with unknown email → 401 with generic detail."""
    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": "nobody@example.com", "password": "correct horse battery staple"},
    )
    assert resp.status_code == 401
    assert resp.json() == {"detail": "Invalid credentials."}


@pytest.mark.asyncio
async def test_login_wrong_password_returns_401(client, db_session):
    """POST /login with correct email but wrong password → 401, same detail."""
    user = await _register(db_session)
    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": user.email, "password": "wrong-password-xyz"},
    )
    assert resp.status_code == 401
    assert resp.json() == {"detail": "Invalid credentials."}


@pytest.mark.asyncio
async def test_login_inactive_user_returns_401(client, db_session):
    """POST /login with inactive account → 401, same generic detail."""
    user = await _register(db_session, is_active=False)
    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": user.email, "password": "correct horse battery staple"},
    )
    assert resp.status_code == 401
    assert resp.json() == {"detail": "Invalid credentials."}


# ---------------------------------------------------------------------------
# /me tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_me_returns_current_user(client, db_session):
    """Login then GET /me → 200 with correct user id and email."""
    user = await _register(db_session)
    # Login to obtain auth cookie
    login_resp = await client.post(
        "/api/v1/auth/login",
        json={"email": user.email, "password": "correct horse battery staple"},
    )
    assert login_resp.status_code == 200

    # httpx AsyncClient stores cookies automatically
    me_resp = await client.get("/api/v1/auth/me")
    assert me_resp.status_code == 200
    body = me_resp.json()
    assert body["user"]["id"] == str(user.id)
    assert body["user"]["email"] == user.email


@pytest.mark.asyncio
async def test_me_returns_401_without_cookie(client, db_session):
    """GET /me with no cookies → 401."""
    resp = await client.get("/api/v1/auth/me")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_me_does_not_rotate_access_token(client, db_session):
    """GET /me must NOT issue a new auth cookie (no token rotation)."""
    user = await _register(db_session)
    await client.post(
        "/api/v1/auth/login",
        json={"email": user.email, "password": "correct horse battery staple"},
    )

    me_resp = await client.get("/api/v1/auth/me")
    assert me_resp.status_code == 200

    # The /me response must not set a new auth cookie
    auth_cookie_header = _get_set_cookie_header(me_resp, settings.AUTH_COOKIE_NAME)
    assert auth_cookie_header is None, "GET /me must not set a new auth cookie (no token rotation)"


# ---------------------------------------------------------------------------
# Logout tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_logout_clears_both_cookies(client, db_session):
    """Logout → 200, both cookies cleared (max-age=0 or deleted)."""
    user = await _register(db_session)
    await client.post(
        "/api/v1/auth/login",
        json={"email": user.email, "password": "correct horse battery staple"},
    )

    logout_resp = await client.post("/api/v1/auth/logout")
    assert logout_resp.status_code == 200
    assert logout_resp.json() == {"message": "Logged out."}

    # Both cookies should appear in Set-Cookie with max-age=0 (deleted)
    auth_raw = _get_set_cookie_header(logout_resp, settings.AUTH_COOKIE_NAME)
    csrf_raw = _get_set_cookie_header(logout_resp, settings.CSRF_COOKIE_NAME)

    assert auth_raw is not None, "Logout should set auth cookie with max-age=0"
    assert csrf_raw is not None, "Logout should set CSRF cookie with max-age=0"

    # Starlette's delete_cookie sets max-age=0
    assert "max-age=0" in auth_raw.lower()
    assert "max-age=0" in csrf_raw.lower()


@pytest.mark.asyncio
async def test_logout_is_idempotent(client, db_session):
    """Two consecutive logout calls both return 200."""
    user = await _register(db_session)
    await client.post(
        "/api/v1/auth/login",
        json={"email": user.email, "password": "correct horse battery staple"},
    )

    resp1 = await client.post("/api/v1/auth/logout")
    assert resp1.status_code == 200

    # Second call — no cookies present at this point
    resp2 = await client.post("/api/v1/auth/logout")
    assert resp2.status_code == 200


@pytest.mark.asyncio
async def test_logout_succeeds_with_missing_cookie(client, db_session):
    """POST /logout with no cookies → 200 (no auth required)."""
    resp = await client.post("/api/v1/auth/logout")
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Security / schema tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_response_schema_does_not_expose_password_hash(client, db_session):
    """Login response body must not contain hashed_password or password fields."""
    user = await _register(db_session)
    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": user.email, "password": "correct horse battery staple"},
    )
    assert resp.status_code == 200
    body_text = resp.text
    assert "hashed_password" not in body_text
    # 'password' should not appear as a top-level key in the JSON body
    body = resp.json()
    assert "password" not in body
