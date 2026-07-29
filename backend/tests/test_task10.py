"""
tests/test_task10.py
====================
Focused tests for Task 10: CSRF enforcement, authentication protection,
role-based access control, user-management CSRF, CSV import protection,
and CORS behavior.

Testing strategy
----------------
- Use the real `client` fixture (no auth/CSRF overrides) for all tests
  that exercise authentication, CSRF, or role-enforcement boundaries.
- Use `authed_client` only where auth itself is not under test (not used here).
- Real DB users are created for each role under test.
- Real JWTs are minted via create_access_token with the user's DB role.
- CSRF tokens are explicit pairs of matching cookie + header values.
"""

from __future__ import annotations

import io
import uuid as _uuid

import pytest

from app.core.config import settings
from app.core.security import create_access_token
from app.models.user import UserRole
from app.services.auth_service import AuthService

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_CSRF_TOKEN = "test-task10-csrf-token"

# A minimal valid CSV for import tests
_VALID_CSV = (
    "dataset_name,source_name,indicator_code,province_code,value,reference_year\n"
    "TestDataset,TestSource,POVERTY_RATE,CP,42.5,2022\n"
)


def _unique_email() -> str:
    return f"t10-{_uuid.uuid4().hex[:8]}@example.com"


def _auth_cookie(user_id, role: UserRole) -> dict:
    """Return {AUTH_COOKIE_NAME: signed_jwt} for use in httpx cookies=."""
    token = create_access_token(user_id=user_id, role=role)
    return {settings.AUTH_COOKIE_NAME: token}


def _csrf_pair() -> tuple[dict, dict]:
    """Return (cookies_dict, headers_dict) with a matching CSRF token."""
    return (
        {settings.CSRF_COOKIE_NAME: _CSRF_TOKEN},
        {settings.CSRF_HEADER_NAME: _CSRF_TOKEN},
    )


def _full_cookies(user_id, role: UserRole) -> dict:
    """Auth cookie + CSRF cookie combined."""
    c = _auth_cookie(user_id, role)
    c[settings.CSRF_COOKIE_NAME] = _CSRF_TOKEN
    return c


async def _make_user(db_session, role: UserRole, email: str | None = None):
    """Create a real active user via AuthService and flush."""
    svc = AuthService(db_session)
    user = await svc.create_user(
        email=email or _unique_email(),
        password="correct horse battery staple",
        full_name=f"{role.value} User",
        role=role,
        is_active=True,
    )
    await db_session.flush()
    return user


# ---------------------------------------------------------------------------
# CSRF dependency tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_csrf_get_succeeds_without_csrf(client, db_session):
    """GET on a protected endpoint passes without any CSRF token."""
    user = await _make_user(db_session, UserRole.VIEWER)
    resp = await client.get(
        "/api/v1/provinces",
        cookies=_auth_cookie(user.id, user.role),
    )
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_csrf_post_without_csrf_cookie_returns_403(client, db_session):
    """POST with no CSRF cookie → 403 CSRF failure."""
    user = await _make_user(db_session, UserRole.ADMIN)
    auth_cookies = _auth_cookie(user.id, user.role)
    # Has header but no cookie
    resp = await client.post(
        "/api/v1/users",
        json={"email": _unique_email(), "password": "validpassword123", "role": "VIEWER"},
        cookies=auth_cookies,
        headers={settings.CSRF_HEADER_NAME: _CSRF_TOKEN},
    )
    assert resp.status_code == 403
    assert resp.json()["detail"] == "CSRF validation failed."


@pytest.mark.asyncio
async def test_csrf_post_without_csrf_header_returns_403(client, db_session):
    """POST with CSRF cookie but no CSRF header → 403."""
    user = await _make_user(db_session, UserRole.ADMIN)
    cookies = _auth_cookie(user.id, user.role)
    cookies[settings.CSRF_COOKIE_NAME] = _CSRF_TOKEN
    resp = await client.post(
        "/api/v1/users",
        json={"email": _unique_email(), "password": "validpassword123", "role": "VIEWER"},
        cookies=cookies,
        # no CSRF header
    )
    assert resp.status_code == 403
    assert resp.json()["detail"] == "CSRF validation failed."


@pytest.mark.asyncio
async def test_csrf_blank_cookie_returns_403(client, db_session):
    """POST with blank CSRF cookie value → 403."""
    user = await _make_user(db_session, UserRole.ADMIN)
    cookies = _auth_cookie(user.id, user.role)
    cookies[settings.CSRF_COOKIE_NAME] = "   "   # blank
    resp = await client.post(
        "/api/v1/users",
        json={"email": _unique_email(), "password": "validpassword123", "role": "VIEWER"},
        cookies=cookies,
        headers={settings.CSRF_HEADER_NAME: _CSRF_TOKEN},
    )
    assert resp.status_code == 403
    assert resp.json()["detail"] == "CSRF validation failed."


@pytest.mark.asyncio
async def test_csrf_blank_header_returns_403(client, db_session):
    """POST with blank CSRF header value → 403."""
    user = await _make_user(db_session, UserRole.ADMIN)
    cookies = _auth_cookie(user.id, user.role)
    cookies[settings.CSRF_COOKIE_NAME] = _CSRF_TOKEN
    resp = await client.post(
        "/api/v1/users",
        json={"email": _unique_email(), "password": "validpassword123", "role": "VIEWER"},
        cookies=cookies,
        headers={settings.CSRF_HEADER_NAME: "   "},  # blank
    )
    assert resp.status_code == 403
    assert resp.json()["detail"] == "CSRF validation failed."


@pytest.mark.asyncio
async def test_csrf_mismatched_values_returns_403(client, db_session):
    """POST with cookie='tokenA' and header='tokenB' → 403."""
    user = await _make_user(db_session, UserRole.ADMIN)
    cookies = _auth_cookie(user.id, user.role)
    cookies[settings.CSRF_COOKIE_NAME] = "tokenA"
    resp = await client.post(
        "/api/v1/users",
        json={"email": _unique_email(), "password": "validpassword123", "role": "VIEWER"},
        cookies=cookies,
        headers={settings.CSRF_HEADER_NAME: "tokenB"},
    )
    assert resp.status_code == 403
    assert resp.json()["detail"] == "CSRF validation failed."


@pytest.mark.asyncio
async def test_csrf_matching_values_succeed(client, db_session):
    """POST with matching CSRF cookie and header passes CSRF check."""
    user = await _make_user(db_session, UserRole.ADMIN)
    csrf_c, csrf_h = _csrf_pair()
    cookies = {**_auth_cookie(user.id, user.role), **csrf_c}
    resp = await client.post(
        "/api/v1/users",
        json={"email": _unique_email(), "password": "validpassword123", "role": "VIEWER"},
        cookies=cookies,
        headers=csrf_h,
    )
    # Should reach the endpoint (201 created or 409 if duplicate — not 403)
    assert resp.status_code in (201, 409)


@pytest.mark.asyncio
async def test_csrf_error_detail_is_generic(client, db_session):
    """403 detail is exactly 'CSRF validation failed.' — no cookie/header specifics."""
    user = await _make_user(db_session, UserRole.ADMIN)
    resp = await client.post(
        "/api/v1/users",
        json={"email": _unique_email(), "password": "validpassword123", "role": "VIEWER"},
        cookies=_auth_cookie(user.id, user.role),
        # no CSRF at all
    )
    assert resp.status_code == 403
    body = resp.json()
    assert body == {"detail": "CSRF validation failed."}
    # Token values must not appear in the error body
    assert _CSRF_TOKEN not in str(body)


@pytest.mark.asyncio
async def test_csrf_token_never_exposed_in_response(client, db_session):
    """The CSRF 403 response body never contains the actual token value."""
    user = await _make_user(db_session, UserRole.ADMIN)
    secret_token = "super-secret-csrf-value-xyz"
    cookies = _auth_cookie(user.id, user.role)
    cookies[settings.CSRF_COOKIE_NAME] = secret_token
    resp = await client.post(
        "/api/v1/users",
        json={"email": _unique_email(), "password": "validpassword123", "role": "VIEWER"},
        cookies=cookies,
        headers={settings.CSRF_HEADER_NAME: "wrong-value"},
    )
    assert resp.status_code == 403
    assert secret_token not in resp.text


# ---------------------------------------------------------------------------
# Authentication protection tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_protected_endpoint_without_auth_returns_401(client):
    """GET on a protected endpoint without any auth cookie → 401."""
    resp = await client.get("/api/v1/provinces")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_health_endpoint_is_public(client):
    """GET /health requires no authentication."""
    resp = await client.get("/api/v1/health")
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_login_works_without_csrf(client, db_session):
    """POST /auth/login does not require a CSRF token."""
    user = await _make_user(db_session, UserRole.VIEWER)
    resp = await client.post(
        "/api/v1/auth/login",
        json={"email": user.email, "password": "correct horse battery staple"},
        # no CSRF cookie, no CSRF header
    )
    # Should succeed (200) or fail with credentials error (401) — not a CSRF 403
    assert resp.status_code != 403


# ---------------------------------------------------------------------------
# Role enforcement tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_admin_can_create_user(client, db_session):
    """ADMIN role can successfully create a user (mutation allowed)."""
    admin = await _make_user(db_session, UserRole.ADMIN)
    csrf_c, csrf_h = _csrf_pair()
    cookies = {**_auth_cookie(admin.id, admin.role), **csrf_c}
    resp = await client.post(
        "/api/v1/users",
        json={"email": _unique_email(), "password": "validpassword123", "role": "VIEWER"},
        cookies=cookies,
        headers=csrf_h,
    )
    assert resp.status_code == 201


@pytest.mark.asyncio
async def test_data_manager_cannot_create_user(client, db_session):
    """DATA_MANAGER cannot access user-management endpoints (ADMIN only)."""
    dm = await _make_user(db_session, UserRole.DATA_MANAGER)
    csrf_c, csrf_h = _csrf_pair()
    cookies = {**_auth_cookie(dm.id, dm.role), **csrf_c}
    resp = await client.post(
        "/api/v1/users",
        json={"email": _unique_email(), "password": "validpassword123", "role": "VIEWER"},
        cookies=cookies,
        headers=csrf_h,
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_analyst_cannot_create_user(client, db_session):
    """ANALYST cannot access user-management endpoints."""
    analyst = await _make_user(db_session, UserRole.ANALYST)
    csrf_c, csrf_h = _csrf_pair()
    cookies = {**_auth_cookie(analyst.id, analyst.role), **csrf_c}
    resp = await client.post(
        "/api/v1/users",
        json={"email": _unique_email(), "password": "validpassword123", "role": "VIEWER"},
        cookies=cookies,
        headers=csrf_h,
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_viewer_cannot_create_user(client, db_session):
    """VIEWER cannot access user-management endpoints."""
    viewer = await _make_user(db_session, UserRole.VIEWER)
    csrf_c, csrf_h = _csrf_pair()
    cookies = {**_auth_cookie(viewer.id, viewer.role), **csrf_c}
    resp = await client.post(
        "/api/v1/users",
        json={"email": _unique_email(), "password": "validpassword123", "role": "VIEWER"},
        cookies=cookies,
        headers=csrf_h,
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_viewer_can_read_analytics(client, db_session):
    """VIEWER can access the analytics endpoint (read-only allowed)."""
    viewer = await _make_user(db_session, UserRole.VIEWER)
    resp = await client.get(
        "/api/v1/analytics/indicator-summary",
        params={"indicator_id": str(_uuid.uuid4()), "reference_year": 2022},
        cookies=_auth_cookie(viewer.id, viewer.role),
    )
    # 404 (no such indicator) or 409 (ambiguous) — not 401 or 403
    assert resp.status_code not in (401, 403)


@pytest.mark.asyncio
async def test_analyst_can_read_analytics(client, db_session):
    """ANALYST can access the analytics endpoint (read-only allowed)."""
    analyst = await _make_user(db_session, UserRole.ANALYST)
    resp = await client.get(
        "/api/v1/analytics/indicator-summary",
        params={"indicator_id": str(_uuid.uuid4()), "reference_year": 2022},
        cookies=_auth_cookie(analyst.id, analyst.role),
    )
    assert resp.status_code not in (401, 403)


@pytest.mark.asyncio
async def test_jwt_role_mismatch_does_not_override_db_role(client, db_session):
    """Minting a JWT with ADMIN role for a DB VIEWER does not grant ADMIN access."""
    viewer = await _make_user(db_session, UserRole.VIEWER)
    # Mint token claiming ADMIN role — DB role is VIEWER
    spoofed_cookies = _auth_cookie(viewer.id, UserRole.ADMIN)  # wrong role in token
    csrf_c, csrf_h = _csrf_pair()
    cookies = {**spoofed_cookies, **csrf_c}
    resp = await client.post(
        "/api/v1/users",
        json={"email": _unique_email(), "password": "validpassword123", "role": "VIEWER"},
        cookies=cookies,
        headers=csrf_h,
    )
    # DB role VIEWER is loaded — must get 403, not 201
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# User-management CSRF tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_admin_user_mutation_without_csrf_returns_403(client, db_session):
    """ADMIN POST /users without CSRF → 403 (CSRF required for mutations)."""
    admin = await _make_user(db_session, UserRole.ADMIN)
    resp = await client.post(
        "/api/v1/users",
        json={"email": _unique_email(), "password": "validpassword123", "role": "VIEWER"},
        cookies=_auth_cookie(admin.id, admin.role),
        # no CSRF
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_admin_user_mutation_with_csrf_succeeds(client, db_session):
    """ADMIN POST /users with valid CSRF → 201."""
    admin = await _make_user(db_session, UserRole.ADMIN)
    csrf_c, csrf_h = _csrf_pair()
    cookies = {**_auth_cookie(admin.id, admin.role), **csrf_c}
    resp = await client.post(
        "/api/v1/users",
        json={"email": _unique_email(), "password": "validpassword123", "role": "VIEWER"},
        cookies=cookies,
        headers=csrf_h,
    )
    assert resp.status_code == 201


@pytest.mark.asyncio
async def test_admin_user_get_does_not_require_csrf(client, db_session):
    """ADMIN GET /users requires auth but no CSRF (GET is a safe method)."""
    admin = await _make_user(db_session, UserRole.ADMIN)
    resp = await client.get(
        "/api/v1/users",
        cookies=_auth_cookie(admin.id, admin.role),
        # no CSRF cookie or header
    )
    assert resp.status_code == 200


# ---------------------------------------------------------------------------
# CSV import tests
# ---------------------------------------------------------------------------


def _make_csv_file(content: str = _VALID_CSV) -> tuple:
    """Return (files_dict, content_type) for httpx multipart upload."""
    return (
        {"file": ("test.csv", io.BytesIO(content.encode()), "text/csv")},
    )


@pytest.mark.asyncio
async def test_import_unauthenticated_returns_401(client):
    """POST /imports/csv/preview without auth cookie → 401."""
    files = {"file": ("test.csv", io.BytesIO(_VALID_CSV.encode()), "text/csv")}
    resp = await client.post("/api/v1/imports/csv/preview", files=files)
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_import_wrong_role_returns_403(client, db_session):
    """ANALYST cannot access import endpoint → 403."""
    analyst = await _make_user(db_session, UserRole.ANALYST)
    csrf_c, csrf_h = _csrf_pair()
    cookies = {**_auth_cookie(analyst.id, analyst.role), **csrf_c}
    files = {"file": ("test.csv", io.BytesIO(_VALID_CSV.encode()), "text/csv")}
    resp = await client.post(
        "/api/v1/imports/csv/preview",
        files=files,
        cookies=cookies,
        headers=csrf_h,
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_import_missing_csrf_returns_403(client, db_session):
    """DATA_MANAGER with auth but no CSRF cookie/header → 403."""
    dm = await _make_user(db_session, UserRole.DATA_MANAGER)
    files = {"file": ("test.csv", io.BytesIO(_VALID_CSV.encode()), "text/csv")}
    resp = await client.post(
        "/api/v1/imports/csv/preview",
        files=files,
        cookies=_auth_cookie(dm.id, dm.role),
        # no CSRF
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_import_mismatched_csrf_returns_403(client, db_session):
    """DATA_MANAGER with mismatched CSRF values → 403."""
    dm = await _make_user(db_session, UserRole.DATA_MANAGER)
    cookies = _auth_cookie(dm.id, dm.role)
    cookies[settings.CSRF_COOKIE_NAME] = "cookie-value"
    files = {"file": ("test.csv", io.BytesIO(_VALID_CSV.encode()), "text/csv")}
    resp = await client.post(
        "/api/v1/imports/csv/preview",
        files=files,
        cookies=cookies,
        headers={settings.CSRF_HEADER_NAME: "header-value"},  # mismatch
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_import_admin_with_valid_csrf_reaches_endpoint(client, db_session):
    """ADMIN with valid CSRF reaches the import endpoint (200 or 422, not 401/403)."""
    admin = await _make_user(db_session, UserRole.ADMIN)
    csrf_c, csrf_h = _csrf_pair()
    cookies = {**_auth_cookie(admin.id, admin.role), **csrf_c}
    files = {"file": ("test.csv", io.BytesIO(_VALID_CSV.encode()), "text/csv")}
    resp = await client.post(
        "/api/v1/imports/csv/preview",
        files=files,
        cookies=cookies,
        headers=csrf_h,
    )
    assert resp.status_code not in (401, 403)


@pytest.mark.asyncio
async def test_import_data_manager_with_valid_csrf_reaches_endpoint(client, db_session):
    """DATA_MANAGER with valid CSRF reaches the import endpoint (not 401/403)."""
    dm = await _make_user(db_session, UserRole.DATA_MANAGER)
    csrf_c, csrf_h = _csrf_pair()
    cookies = {**_auth_cookie(dm.id, dm.role), **csrf_c}
    files = {"file": ("test.csv", io.BytesIO(_VALID_CSV.encode()), "text/csv")}
    resp = await client.post(
        "/api/v1/imports/csv/preview",
        files=files,
        cookies=cookies,
        headers=csrf_h,
    )
    assert resp.status_code not in (401, 403)


# ---------------------------------------------------------------------------
# CORS tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cors_configured_origin_receives_allow_credentials(client):
    """A credentialed request from the configured origin gets Allow-Credentials: true."""
    origin = settings.CORS_ORIGINS[0]
    resp = await client.get(
        "/api/v1/health",
        headers={"Origin": origin},
    )
    assert resp.status_code == 200
    assert resp.headers.get("access-control-allow-credentials") == "true"


@pytest.mark.asyncio
async def test_cors_configured_origin_receives_correct_allow_origin(client):
    """The configured origin receives its own value in Allow-Origin header."""
    origin = settings.CORS_ORIGINS[0]
    resp = await client.get(
        "/api/v1/health",
        headers={"Origin": origin},
    )
    assert resp.status_code == 200
    assert resp.headers.get("access-control-allow-origin") == origin


@pytest.mark.asyncio
async def test_cors_unapproved_origin_not_granted_credentialed_access(client):
    """An unapproved origin must not receive Access-Control-Allow-Origin."""
    resp = await client.get(
        "/api/v1/health",
        headers={"Origin": "https://evil.example.com"},
    )
    # Either no header or it must not be the evil origin
    allow_origin = resp.headers.get("access-control-allow-origin", "")
    assert allow_origin != "https://evil.example.com"


@pytest.mark.asyncio
async def test_cors_csrf_header_allowed_in_preflight(client):
    """OPTIONS preflight for the CSRF header must include it in Access-Control-Allow-Headers."""
    origin = settings.CORS_ORIGINS[0]
    resp = await client.options(
        "/api/v1/users",
        headers={
            "Origin": origin,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": settings.CSRF_HEADER_NAME,
        },
    )
    # 200 or 204 for preflight
    assert resp.status_code in (200, 204)
    allow_headers = resp.headers.get("access-control-allow-headers", "").lower()
    # With allow_headers=["*"], all headers are permitted
    assert "*" in allow_headers or settings.CSRF_HEADER_NAME.lower() in allow_headers
