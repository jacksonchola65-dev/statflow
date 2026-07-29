"""
tests/test_dependencies.py
==========================
Integration tests for core/dependencies.py.

Strategy
--------
- A minimal test router is registered on the real app (with the test DB
  override already in place via the `client` fixture from conftest.py).
- Users are created via AuthService to exercise the real DB path.
- JWTs are minted via create_access_token (valid) or built by hand (expired).
- The tests drive the app through the httpx AsyncClient, so the full FastAPI
  request / dependency-injection pipeline is exercised.
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
import pytest_asyncio
from httpx import AsyncClient

from app.core.config import settings
from app.core.dependencies import (
    get_current_user,
    require_admin,
    require_data_manager_or_admin,
)
from app.core.security import create_access_token
from app.models.user import User, UserRole
from app.services.auth_service import AuthService

# ---------------------------------------------------------------------------
# Test router — registered on the app at fixture setup time
# ---------------------------------------------------------------------------

from fastapi import APIRouter, Depends

test_router = APIRouter()


@test_router.get("/test/me")
async def route_me(user: User = Depends(get_current_user)):
    return {"id": str(user.id), "role": user.role.value}


@test_router.get("/test/admin-only")
async def route_admin(user: User = Depends(require_admin)):
    return {"id": str(user.id)}


@test_router.get("/test/data-manager-or-admin")
async def route_dm(user: User = Depends(require_data_manager_or_admin)):
    return {"id": str(user.id)}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _auth_cookie(user_id: uuid.UUID, role: UserRole) -> dict:
    """Return {cookie_name: token} to pass as cookies= in httpx."""
    token = create_access_token(user_id=user_id, role=role)
    return {settings.AUTH_COOKIE_NAME: token}


def _expired_token(user_id: uuid.UUID, role: UserRole) -> str:
    """Build a JWT whose exp is 1 second in the past."""
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "exp": now - timedelta(seconds=1),
        "iat": now - timedelta(hours=1),
        "jti": str(uuid.uuid4()),
        "role": role.value,
    }
    return _jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture
async def auth_client(db_session, client: AsyncClient) -> AsyncClient:
    """Attach the test router to the app that the client is already wired to.

    The `client` fixture (from conftest.py) creates a fresh FastAPI app and
    overrides get_db.  We include test_router on that same app instance so
    the /test/* routes are available — and the DB override still applies.
    """
    # Retrieve the app from the transport
    app = client._transport.app  # type: ignore[attr-defined]
    app.include_router(test_router)
    return client


async def _make_user(
    db_session,
    *,
    email: str | None = None,
    role: UserRole = UserRole.VIEWER,
    is_active: bool = True,
) -> User:
    """Convenience: create a user via AuthService and flush to DB."""
    if email is None:
        email = f"user-{uuid.uuid4().hex[:8]}@example.com"
    svc = AuthService(db_session)
    user = await svc.create_user(
        email=email,
        password="SecurePassw0rd!xyz",
        full_name="Test User",
        role=role,
        is_active=is_active,
    )
    await db_session.flush()
    return user


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_valid_cookie_returns_user(db_session, auth_client):
    """Active user with a valid JWT cookie → 200 with correct user id."""
    user = await _make_user(db_session, role=UserRole.VIEWER)
    resp = await auth_client.get("/test/me", cookies=_auth_cookie(user.id, user.role))
    assert resp.status_code == 200
    assert resp.json()["id"] == str(user.id)


@pytest.mark.asyncio
async def test_missing_cookie_returns_401(auth_client):
    """No cookie at all → 401."""
    resp = await auth_client.get("/test/me")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_malformed_token_returns_401(auth_client):
    """Cookie present but value is not a JWT → 401."""
    resp = await auth_client.get(
        "/test/me", cookies={settings.AUTH_COOKIE_NAME: "not-a-jwt"}
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_expired_token_returns_401(db_session, auth_client):
    """Cookie holds an expired token → 401."""
    user = await _make_user(db_session)
    expired = _expired_token(user.id, user.role)
    resp = await auth_client.get(
        "/test/me", cookies={settings.AUTH_COOKIE_NAME: expired}
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_token_for_missing_user_returns_401(auth_client):
    """JWT sub references a UUID not in the DB → 401."""
    phantom_id = uuid.uuid4()
    resp = await auth_client.get(
        "/test/me", cookies=_auth_cookie(phantom_id, UserRole.VIEWER)
    )
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_token_for_inactive_user_returns_401(db_session, auth_client):
    """Valid JWT for an inactive user → 401."""
    user = await _make_user(db_session, is_active=False)
    resp = await auth_client.get("/test/me", cookies=_auth_cookie(user.id, user.role))
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_db_role_is_authoritative(db_session, auth_client):
    """JWT claims ADMIN but DB role is VIEWER → 403 on admin-only endpoint."""
    user = await _make_user(db_session, role=UserRole.VIEWER)
    # Mint a token that falsely claims ADMIN role
    spoofed_cookie = {
        settings.AUTH_COOKIE_NAME: create_access_token(
            user_id=user.id, role=UserRole.ADMIN
        )
    }
    resp = await auth_client.get("/test/admin-only", cookies=spoofed_cookie)
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_allowed_role_succeeds(db_session, auth_client):
    """ADMIN user accessing admin-only endpoint → 200."""
    user = await _make_user(db_session, role=UserRole.ADMIN)
    resp = await auth_client.get("/test/admin-only", cookies=_auth_cookie(user.id, user.role))
    assert resp.status_code == 200
    assert resp.json()["id"] == str(user.id)


@pytest.mark.asyncio
async def test_disallowed_role_returns_403(db_session, auth_client):
    """VIEWER user accessing admin-only endpoint → 403."""
    user = await _make_user(db_session, role=UserRole.VIEWER)
    resp = await auth_client.get("/test/admin-only", cookies=_auth_cookie(user.id, user.role))
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_401_contains_www_authenticate_header(auth_client):
    """Missing cookie → response carries WWW-Authenticate: Bearer header."""
    resp = await auth_client.get("/test/me")
    assert resp.status_code == 401
    assert resp.headers.get("www-authenticate") == "Bearer"


@pytest.mark.asyncio
async def test_401_uses_generic_detail(auth_client):
    """Missing cookie → body is exactly {"detail": "Authentication required."}."""
    resp = await auth_client.get("/test/me")
    assert resp.status_code == 401
    assert resp.json() == {"detail": "Authentication required."}


@pytest.mark.asyncio
async def test_403_uses_insufficient_permissions_detail(db_session, auth_client):
    """VIEWER on admin-only route → body is {"detail": "Insufficient permissions."}."""
    user = await _make_user(db_session, role=UserRole.VIEWER)
    resp = await auth_client.get("/test/admin-only", cookies=_auth_cookie(user.id, user.role))
    assert resp.status_code == 403
    assert resp.json() == {"detail": "Insufficient permissions."}


@pytest.mark.asyncio
async def test_data_manager_can_access_dm_endpoint(db_session, auth_client):
    """DATA_MANAGER user accessing data-manager-or-admin endpoint → 200."""
    user = await _make_user(db_session, role=UserRole.DATA_MANAGER)
    resp = await auth_client.get(
        "/test/data-manager-or-admin", cookies=_auth_cookie(user.id, user.role)
    )
    assert resp.status_code == 200
    assert resp.json()["id"] == str(user.id)


@pytest.mark.asyncio
async def test_viewer_cannot_access_dm_endpoint(db_session, auth_client):
    """VIEWER user accessing data-manager-or-admin endpoint → 403."""
    user = await _make_user(db_session, role=UserRole.VIEWER)
    resp = await auth_client.get(
        "/test/data-manager-or-admin", cookies=_auth_cookie(user.id, user.role)
    )
    assert resp.status_code == 403
