"""
tests/test_auth.py
==================
Endpoint tests for POST /api/v1/auth/login and GET /api/v1/auth/me.

Covers REQ-13.3 and REQ-13.4:
  REQ-13.3: Login endpoint: correct credentials → 200 + token; wrong password → 401;
            unknown email → 401; inactive user → 401.
  REQ-13.4: Protected endpoint (/auth/me): valid token → 200; missing token → 401;
            invalid token → 401; expired token → 401.
"""

from __future__ import annotations

import sys

if sys.platform == "win32":
    import asyncio as _asyncio
    _asyncio.set_event_loop_policy(_asyncio.WindowsSelectorEventLoopPolicy())

import uuid
from datetime import datetime, timedelta, timezone

import jwt as _jwt
import pytest

from app.core.config import settings
from app.core.security import create_access_token
from app.models.user import UserRole


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _unique_email() -> str:
    return f"auth-test-{uuid.uuid4().hex[:8]}@example.com"


async def _create_user(
    db_session,
    *,
    email: str | None = None,
    password: str = "correct horse battery staple",
    role: UserRole = UserRole.VIEWER,
    is_active: bool = True,
):
    """Create a user via AuthService and flush to DB."""
    from app.services.auth_service import AuthService

    svc = AuthService(db_session)
    user = await svc.create_user(
        email=email or _unique_email(),
        password=password,
        full_name="Auth Test User",
        role=role,
        is_active=is_active,
    )
    await db_session.flush()
    return user


def _expired_cookie(user_id: uuid.UUID, role: UserRole) -> dict:
    """Build a cookie dict with an expired JWT."""
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "exp": now - timedelta(seconds=1),
        "iat": now - timedelta(hours=1),
        "jti": str(uuid.uuid4()),
        "role": role.value,
        "email": "expired@example.com",
    }
    token = _jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)
    return {settings.AUTH_COOKIE_NAME: token}


# ---------------------------------------------------------------------------
# REQ-13.3 — Login endpoint
# ---------------------------------------------------------------------------


async def test_login_correct_credentials_returns_200(client, db_session):
    """Correct credentials → 200 with token info and user data."""
    user = await _create_user(db_session)
    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": user.email, "password": "correct horse battery staple"},
    )
    assert resp.status_code == 200
    body = resp.json()
    # Response includes user info and CSRF token
    assert "user" in body
    assert body["user"]["id"] == str(user.id)
    assert body["csrf_token"]
    assert body["expires_in"] > 0


async def test_login_sets_auth_cookie(client, db_session):
    """Successful login → auth cookie is set in response."""
    user = await _create_user(db_session)
    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": user.email, "password": "correct horse battery staple"},
    )
    assert resp.status_code == 200
    # httpx stores cookies; the auth cookie should be present
    assert settings.AUTH_COOKIE_NAME in client.cookies


async def test_login_wrong_password_returns_401(client, db_session):
    """Wrong password → 401 with generic 'Invalid credentials.' message (REQ-13.3)."""
    user = await _create_user(db_session)
    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": user.email, "password": "totally-wrong-password"},
    )
    assert resp.status_code == 401
    assert resp.json()["detail"] == "Invalid credentials."


async def test_login_unknown_email_returns_401(client, db_session):
    """Unknown email → 401 with generic 'Invalid credentials.' message (REQ-13.3)."""
    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": "nobody@notexist.example.com", "password": "correct horse battery staple"},
    )
    assert resp.status_code == 401
    assert resp.json()["detail"] == "Invalid credentials."


async def test_login_inactive_user_returns_401(client, db_session):
    """Inactive account → 401 with generic message (REQ-13.3)."""
    user = await _create_user(db_session, is_active=False)
    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": user.email, "password": "correct horse battery staple"},
    )
    assert resp.status_code == 401
    assert resp.json()["detail"] == "Invalid credentials."


async def test_login_all_failure_modes_return_same_message(client, db_session):
    """All three login failure modes return the identical error body (REQ-4.2 / REQ-13.3)."""
    user = await _create_user(db_session, is_active=False)

    resp_unknown = await client.post(
        "/api/v1/auth/login",
        json={"email": "nobody@notexist.example.com", "password": "correct horse battery staple"},
    )
    resp_wrong_pw = await client.post(
        "/api/v1/auth/login",
        json={"email": user.email, "password": "wrong-password"},
    )
    resp_inactive = await client.post(
        "/api/v1/auth/login",
        json={"email": user.email, "password": "correct horse battery staple"},
    )

    for resp in (resp_unknown, resp_wrong_pw, resp_inactive):
        assert resp.status_code == 401
        assert resp.json() == {"detail": "Invalid credentials."}


async def test_login_response_does_not_expose_hashed_password(client, db_session):
    """Login response body must never include hashed_password (REQ-1.3)."""
    user = await _create_user(db_session)
    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": user.email, "password": "correct horse battery staple"},
    )
    assert resp.status_code == 200
    assert "hashed_password" not in resp.text


# ---------------------------------------------------------------------------
# REQ-13.4 — Protected endpoint (/auth/me)
# ---------------------------------------------------------------------------


async def test_me_valid_token_returns_200(client, db_session):
    """Valid token (via cookie) → GET /auth/me returns 200 with user data (REQ-13.4)."""
    user = await _create_user(db_session)
    # Login to set cookie
    login_resp = await client.post(
        "/api/v1/auth/login",
        json={"email": user.email, "password": "correct horse battery staple"},
    )
    assert login_resp.status_code == 200

    me_resp = await client.get("/api/v1/auth/me")
    assert me_resp.status_code == 200
    body = me_resp.json()
    assert body["user"]["id"] == str(user.id)
    assert body["user"]["email"] == user.email


async def test_me_missing_token_returns_401(client, db_session):
    """No auth cookie → GET /auth/me returns 401 (REQ-13.4)."""
    resp = await client.get("/api/v1/auth/me")
    assert resp.status_code == 401


async def test_me_invalid_token_returns_401(client, db_session):
    """Invalid (malformed) token → GET /auth/me returns 401 (REQ-13.4)."""
    resp = await client.get(
        "/api/v1/auth/me",
        cookies={settings.AUTH_COOKIE_NAME: "this.is.not.a.jwt"},
    )
    assert resp.status_code == 401


async def test_me_tampered_token_returns_401(client, db_session):
    """Tampered token signature → GET /auth/me returns 401 (REQ-13.4)."""
    user = await _create_user(db_session)
    token = create_access_token(user_id=user.id, role=user.role, email=user.email)
    # Flip a character in the signature segment
    parts = token.split(".")
    sig = parts[2]
    tampered = ("B" if sig[0] == "A" else "A") + sig[1:]
    tampered_token = ".".join([parts[0], parts[1], tampered])

    resp = await client.get(
        "/api/v1/auth/me",
        cookies={settings.AUTH_COOKIE_NAME: tampered_token},
    )
    assert resp.status_code == 401


async def test_me_expired_token_returns_401(client, db_session):
    """Expired token → GET /auth/me returns 401 (REQ-13.4)."""
    user = await _create_user(db_session)
    expired_cookies = _expired_cookie(user.id, user.role)

    resp = await client.get("/api/v1/auth/me", cookies=expired_cookies)
    assert resp.status_code == 401


async def test_me_does_not_return_hashed_password(client, db_session):
    """GET /auth/me response must not include hashed_password (REQ-1.3 / REQ-4.6)."""
    user = await _create_user(db_session)
    await client.post(
        "/api/v1/auth/login",
        json={"email": user.email, "password": "correct horse battery staple"},
    )
    me_resp = await client.get("/api/v1/auth/me")
    assert me_resp.status_code == 200
    assert "hashed_password" not in me_resp.text


async def test_me_returns_csrf_token(client, db_session):
    """GET /auth/me includes a csrf_token in the response body."""
    user = await _create_user(db_session)
    await client.post(
        "/api/v1/auth/login",
        json={"email": user.email, "password": "correct horse battery staple"},
    )
    me_resp = await client.get("/api/v1/auth/me")
    assert me_resp.status_code == 200
    assert me_resp.json()["csrf_token"]
