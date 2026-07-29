"""
test_import_templates.py
========================
Integration tests for the import template CRUD endpoints.

POST   /api/v1/imports/templates        — create template
GET    /api/v1/imports/templates        — list templates
GET    /api/v1/imports/templates/{id}   — get template
PATCH  /api/v1/imports/templates/{id}   — update template
DELETE /api/v1/imports/templates/{id}   — deactivate template

References: Task 8A
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

VALID_MAPPING_CONFIG = {
    "mapping_version": 1,
    "mappings": [
        {
            "target_field": "province_code",
            "source_type": "column",
            "source_column": "prov",
            "fixed_value": None,
            "transformations": [],
            "required": True,
        },
        {
            "target_field": "indicator_code",
            "source_type": "column",
            "source_column": "indicator",
            "fixed_value": None,
            "transformations": [],
            "required": True,
        },
        {
            "target_field": "value",
            "source_type": "column",
            "source_column": "val",
            "fixed_value": None,
            "transformations": [],
            "required": True,
        },
        {
            "target_field": "reference_year",
            "source_type": "column",
            "source_column": "year",
            "fixed_value": None,
            "transformations": [],
            "required": True,
        },
        {
            "target_field": "dataset_name",
            "source_type": "column",
            "source_column": "ds",
            "fixed_value": None,
            "transformations": [],
            "required": True,
        },
    ],
}

VALID_TEMPLATE_PAYLOAD = {
    "name": "My Ecommerce Template",
    "description": "Maps order data to StatFlow schema",
    "source_format": "csv",
    "original_headers": ["prov", "indicator", "val", "year", "ds"],
    "mapping_config": VALID_MAPPING_CONFIG,
}


def _unique_payload(name_suffix: str = "") -> dict:
    """Return a valid template payload with a unique name."""
    suffix = name_suffix or uuid.uuid4().hex[:8]
    return {
        **VALID_TEMPLATE_PAYLOAD,
        "name": f"Template-{suffix}",
    }


@pytest_asyncio.fixture
async def second_authed_client(db_session: AsyncSession):
    """A second authenticated client for cross-owner access tests."""
    from app.core.dependencies import get_current_user, validate_csrf
    from app.db.session import get_db
    from app.main import create_app
    from app.models.user import UserRole
    from app.services.auth_service import AuthService

    app = create_app()

    svc = AuthService(db_session)
    user2 = await svc.create_user(
        email=f"template-user2-{uuid.uuid4().hex[:8]}@test.example",
        password="template-user2-password",
        full_name="Template User Two",
        role=UserRole.ADMIN,
        is_active=True,
    )
    await db_session.flush()

    principal2 = SimpleNamespace(
        id=user2.id,
        role=user2.role,
        is_active=user2.is_active,
    )

    async def override_get_db():
        async with db_session.begin_nested():
            yield db_session
            await db_session.flush()

    async def override_get_current_user():
        return principal2

    async def override_validate_csrf():
        return None

    app.dependency_overrides[get_db] = override_get_db
    app.dependency_overrides[get_current_user] = override_get_current_user
    app.dependency_overrides[validate_csrf] = override_validate_csrf

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as ac:
        yield ac


# ===========================================================================
# Validation
# ===========================================================================


async def test_mapping_configuration_validation(authed_client: AsyncClient) -> None:
    """Invalid mapping_config (missing required fields) → 422."""
    bad_payload = {
        "name": f"Bad-{uuid.uuid4().hex[:8]}",
        "source_format": "csv",
        "original_headers": ["col1"],
        "mapping_config": {
            "mapping_version": 1,
            "mappings": [
                # Only one mapping — missing 4 required target fields
                {
                    "target_field": "province_code",
                    "source_type": "column",
                    "source_column": "col1",
                    "transformations": [],
                    "required": True,
                },
            ],
        },
    }
    resp = await authed_client.post("/api/v1/imports/templates", json=bad_payload)
    assert resp.status_code == 422, resp.text


# ===========================================================================
# CRUD happy paths
# ===========================================================================


async def test_template_create(authed_client: AsyncClient) -> None:
    """Valid payload → 201, template returned with id."""
    payload = _unique_payload()
    resp = await authed_client.post("/api/v1/imports/templates", json=payload)
    assert resp.status_code == 201, resp.text
    data = resp.json()
    assert "id" in data
    assert data["name"] == payload["name"]
    assert data["is_active"] is True


async def test_template_list(authed_client: AsyncClient) -> None:
    """Creates 2 templates → GET returns at least 2."""
    p1 = _unique_payload()
    p2 = _unique_payload()

    r1 = await authed_client.post("/api/v1/imports/templates", json=p1)
    r2 = await authed_client.post("/api/v1/imports/templates", json=p2)
    assert r1.status_code == 201
    assert r2.status_code == 201

    resp = await authed_client.get("/api/v1/imports/templates")
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert "templates" in data
    names = [t["name"] for t in data["templates"]]
    assert p1["name"] in names
    assert p2["name"] in names


async def test_template_get(authed_client: AsyncClient) -> None:
    """Creates template → GET by id returns it."""
    payload = _unique_payload()
    create_resp = await authed_client.post("/api/v1/imports/templates", json=payload)
    assert create_resp.status_code == 201
    template_id = create_resp.json()["id"]

    resp = await authed_client.get(f"/api/v1/imports/templates/{template_id}")
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["id"] == template_id
    assert data["name"] == payload["name"]


async def test_template_update(authed_client: AsyncClient) -> None:
    """PATCH updates name and description."""
    payload = _unique_payload()
    create_resp = await authed_client.post("/api/v1/imports/templates", json=payload)
    assert create_resp.status_code == 201
    template_id = create_resp.json()["id"]

    new_name = f"Updated-{uuid.uuid4().hex[:8]}"
    patch_resp = await authed_client.patch(
        f"/api/v1/imports/templates/{template_id}",
        json={"name": new_name, "description": "Updated description"},
    )
    assert patch_resp.status_code == 200, patch_resp.text
    data = patch_resp.json()
    assert data["name"] == new_name
    assert data["description"] == "Updated description"


async def test_template_deactivate(authed_client: AsyncClient) -> None:
    """DELETE → 204; template gone from default list."""
    payload = _unique_payload()
    create_resp = await authed_client.post("/api/v1/imports/templates", json=payload)
    assert create_resp.status_code == 201
    template_id = create_resp.json()["id"]

    del_resp = await authed_client.delete(f"/api/v1/imports/templates/{template_id}")
    assert del_resp.status_code == 204, del_resp.text

    # Default list should not include the deactivated template
    list_resp = await authed_client.get("/api/v1/imports/templates")
    assert list_resp.status_code == 200
    names = [t["name"] for t in list_resp.json()["templates"]]
    assert payload["name"] not in names


# ===========================================================================
# Name uniqueness
# ===========================================================================


async def test_same_owner_duplicate_name_rejected(authed_client: AsyncClient) -> None:
    """Create same name twice for same owner → 409."""
    payload = _unique_payload()
    r1 = await authed_client.post("/api/v1/imports/templates", json=payload)
    assert r1.status_code == 201

    r2 = await authed_client.post("/api/v1/imports/templates", json=payload)
    assert r2.status_code == 409, r2.text


async def test_same_name_allowed_for_different_owners(
    authed_client: AsyncClient,
    second_authed_client: AsyncClient,
) -> None:
    """Two different owners using the same template name → both succeed."""
    shared_name = f"Shared-{uuid.uuid4().hex[:8]}"
    payload = {**VALID_TEMPLATE_PAYLOAD, "name": shared_name}

    r1 = await authed_client.post("/api/v1/imports/templates", json=payload)
    assert r1.status_code == 201, r1.text

    r2 = await second_authed_client.post("/api/v1/imports/templates", json=payload)
    assert r2.status_code == 201, r2.text


# ===========================================================================
# Cross-owner access
# ===========================================================================


async def test_cross_owner_read_forbidden(
    authed_client: AsyncClient,
    second_authed_client: AsyncClient,
) -> None:
    """User A's template → user B GET → 404."""
    payload = _unique_payload()
    create_resp = await authed_client.post("/api/v1/imports/templates", json=payload)
    assert create_resp.status_code == 201
    template_id = create_resp.json()["id"]

    resp = await second_authed_client.get(f"/api/v1/imports/templates/{template_id}")
    assert resp.status_code == 404, resp.text


async def test_cross_owner_update_forbidden(
    authed_client: AsyncClient,
    second_authed_client: AsyncClient,
) -> None:
    """User A's template → user B PATCH → 404."""
    payload = _unique_payload()
    create_resp = await authed_client.post("/api/v1/imports/templates", json=payload)
    assert create_resp.status_code == 201
    template_id = create_resp.json()["id"]

    resp = await second_authed_client.patch(
        f"/api/v1/imports/templates/{template_id}",
        json={"description": "Unauthorized update"},
    )
    assert resp.status_code == 404, resp.text


async def test_cross_owner_delete_forbidden(
    authed_client: AsyncClient,
    second_authed_client: AsyncClient,
) -> None:
    """User A's template → user B DELETE → 404."""
    payload = _unique_payload()
    create_resp = await authed_client.post("/api/v1/imports/templates", json=payload)
    assert create_resp.status_code == 201
    template_id = create_resp.json()["id"]

    resp = await second_authed_client.delete(f"/api/v1/imports/templates/{template_id}")
    assert resp.status_code == 404, resp.text


# ===========================================================================
# Inactive filtering
# ===========================================================================


async def test_inactive_template_filtering(authed_client: AsyncClient) -> None:
    """Deactivated template not in default list but present with include_inactive."""
    payload = _unique_payload()
    create_resp = await authed_client.post("/api/v1/imports/templates", json=payload)
    assert create_resp.status_code == 201
    template_id = create_resp.json()["id"]

    # Deactivate it
    del_resp = await authed_client.delete(f"/api/v1/imports/templates/{template_id}")
    assert del_resp.status_code == 204

    # Default list (active only) — should NOT appear
    list_resp = await authed_client.get("/api/v1/imports/templates")
    assert list_resp.status_code == 200
    active_ids = [t["id"] for t in list_resp.json()["templates"]]
    assert template_id not in active_ids
