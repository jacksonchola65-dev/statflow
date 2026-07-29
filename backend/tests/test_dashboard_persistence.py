import uuid
from typing import AsyncGenerator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user, validate_csrf
from app.db.session import get_db
from app.main import create_app
from app.models.user import UserRole
from app.services.auth_service import AuthService


def build_dashboard_payload(title: str = "Revenue Overview", description: str = "Saved dashboard", cards=None):
    if cards is None:
        cards = [
            {
                "id": "card-1",
                "title": "Revenue",
                "subtitle": "Snapshot",
                "visualization_type": "bar",
                "size": "medium",
                "order": 0,
                "visualization_snapshot": {"chartType": "bar", "rows": []},
            }
        ]

    return {
        "title": title,
        "description": description,
        "cards": cards,
    }


async def create_other_user(db_session: AsyncSession, email_suffix: str = "other-dashboard"):
    other_service = AuthService(db_session)
    other_user = await other_service.create_user(
        email=f"{email_suffix}-{uuid.uuid4().hex[:8]}@test.example",
        password="auth-dashboard-password-secure",
        full_name="Other Dashboard User",
        role=UserRole.VIEWER,
        is_active=True,
    )
    await db_session.flush()
    return other_user


async def create_other_client(db_session, other_user):
    other_app = create_app()

    async def override_get_db() -> AsyncGenerator:
        yield db_session

    async def override_get_current_user():
        return other_user

    async def override_validate_csrf():
        return None

    other_app.dependency_overrides[get_db] = override_get_db
    other_app.dependency_overrides[get_current_user] = override_get_current_user
    other_app.dependency_overrides[validate_csrf] = override_validate_csrf

    return AsyncClient(
        transport=ASGITransport(app=other_app),
        base_url="http://testserver",
    )


@pytest.mark.asyncio
async def test_dashboard_owner_can_crud_and_other_users_cannot_modify(authed_client, db_session):
    """Dashboard persistence should enforce owner-only CRUD and list the current user's dashboards."""
    payload = build_dashboard_payload()

    create_resp = await authed_client.post("/api/v1/dashboards", json=payload)
    assert create_resp.status_code == 201, create_resp.text
    created = create_resp.json()
    dashboard_id = created["id"]

    list_resp = await authed_client.get("/api/v1/dashboards")
    assert list_resp.status_code == 200, list_resp.text
    listed = list_resp.json()
    assert listed["total"] >= 1
    assert any(item["id"] == dashboard_id for item in listed["dashboards"])

    update_resp = await authed_client.put(
        f"/api/v1/dashboards/{dashboard_id}", json={"title": "Updated Revenue Overview"}
    )
    assert update_resp.status_code == 200, update_resp.text
    assert update_resp.json()["title"] == "Updated Revenue Overview"

    other_user = await create_other_user(db_session)
    async with await create_other_client(db_session, other_user) as other_client:
        forbidden_resp = await other_client.put(
            f"/api/v1/dashboards/{dashboard_id}",
            json={"title": "Should Fail"},
        )
        assert forbidden_resp.status_code == 403, forbidden_resp.text

    delete_resp = await authed_client.delete(f"/api/v1/dashboards/{dashboard_id}")
    assert delete_resp.status_code == 204, delete_resp.text


@pytest.mark.asyncio
async def test_dashboard_authentication_required_for_crud(client):
    payload = build_dashboard_payload()
    create_resp = await client.post("/api/v1/dashboards", json=payload)
    list_resp = await client.get("/api/v1/dashboards")
    retrieve_resp = await client.get("/api/v1/dashboards/00000000-0000-0000-0000-000000000000")
    update_resp = await client.put("/api/v1/dashboards/00000000-0000-0000-0000-000000000000", json={"title": "Nope"})
    delete_resp = await client.delete("/api/v1/dashboards/00000000-0000-0000-0000-000000000000")

    assert create_resp.status_code == 401
    assert list_resp.status_code == 401
    assert retrieve_resp.status_code == 401
    assert update_resp.status_code == 401
    assert delete_resp.status_code == 401


@pytest.mark.asyncio
async def test_dashboard_create_without_cards_and_with_authenticated_owner(authed_client):
    payload = build_dashboard_payload(cards=[])
    create_resp = await authed_client.post("/api/v1/dashboards", json=payload)
    assert create_resp.status_code == 201, create_resp.text
    created = create_resp.json()
    assert created["title"] == "Revenue Overview"
    assert created["owner_id"]
    assert created["cards"] == []


@pytest.mark.asyncio
async def test_dashboard_create_with_multiple_cards_and_deterministic_order(authed_client):
    payload = build_dashboard_payload(
        cards=[
            {"id": "card-2", "title": "Revenue", "subtitle": "Snapshot", "visualization_type": "bar", "size": "small", "order": 2, "visualization_snapshot": {"chartType": "bar", "rows": []}},
            {"id": "card-1", "title": "Revenue", "subtitle": "Snapshot", "visualization_type": "line", "size": "medium", "order": 1, "visualization_snapshot": {"chartType": "line", "rows": []}},
        ]
    )
    create_resp = await authed_client.post("/api/v1/dashboards", json=payload)
    assert create_resp.status_code == 201, create_resp.text
    created = create_resp.json()
    assert [card["order"] for card in created["cards"]] == [1, 2]


@pytest.mark.asyncio
async def test_dashboard_validation_rejects_invalid_payloads(authed_client):
    invalid_cases = [
        ({"description": "Saved dashboard", "cards": []}, 422),
        ({"title": "   ", "description": "Saved dashboard", "cards": []}, 422),
        ({"title": "x" * 121, "description": "Saved dashboard", "cards": []}, 422),
        ({"title": "Revenue", "description": "x" * 501, "cards": []}, 422),
        ({"title": "Revenue", "cards": [{"id": "card-1", "title": "Revenue", "size": "tiny", "order": 0, "visualization_snapshot": {}}]}, 422),
        ({"title": "Revenue", "cards": [{"id": "card-1", "title": "Revenue", "visualization_type": "radar", "order": 0, "visualization_snapshot": {}}]}, 422),
        ({"title": "Revenue", "cards": [{"id": "card-1", "title": "Revenue", "order": 0, "visualization_snapshot": "not-an-object"}]}, 422),
        ({"title": "Revenue", "cards": [{"id": "card-1", "title": "Revenue", "order": 0, "visualization_snapshot": {}}, {"id": "card-1", "title": "Revenue", "order": 1, "visualization_snapshot": {}}]}, 422),
        ({"title": "Revenue", "cards": [{"id": "card-1", "title": "Revenue", "order": 0, "visualization_snapshot": {}}, {"id": "card-2", "title": "Revenue", "order": 0, "visualization_snapshot": {}}]}, 422),
        ({"title": "Revenue", "cards": [{"id": "card-1", "title": "Revenue", "order": -1, "visualization_snapshot": {}}]}, 422),
    ]

    for payload, expected_status in invalid_cases:
        response = await authed_client.post("/api/v1/dashboards", json=payload)
        assert response.status_code == expected_status, (payload, response.text)


@pytest.mark.asyncio
async def test_dashboard_read_and_list_are_owner_scoped(authed_client, db_session):
    payload = build_dashboard_payload(cards=[{"id": "card-1", "title": "Revenue", "order": 0, "visualization_type": "bar", "size": "large", "visualization_snapshot": {"chartType": "bar", "rows": []}}])
    create_resp = await authed_client.post("/api/v1/dashboards", json=payload)
    dashboard_id = create_resp.json()["id"]

    get_resp = await authed_client.get(f"/api/v1/dashboards/{dashboard_id}")
    assert get_resp.status_code == 200, get_resp.text
    get_body = get_resp.json()
    assert get_body["title"] == "Revenue Overview"
    assert [card["order"] for card in get_body["cards"]] == [0]

    list_resp = await authed_client.get("/api/v1/dashboards")
    assert list_resp.status_code == 200, list_resp.text
    listed = list_resp.json()
    assert listed["total"] >= 1

    other_user = await create_other_user(db_session)
    async with await create_other_client(db_session, other_user) as other_client:
        forbidden_get = await other_client.get(f"/api/v1/dashboards/{dashboard_id}")
        assert forbidden_get.status_code == 403

        other_list = await other_client.get("/api/v1/dashboards")
        assert other_list.status_code == 200
        ids = {item["id"] for item in other_list.json()["dashboards"]}
        assert dashboard_id not in ids


@pytest.mark.asyncio
async def test_dashboard_invalid_update_does_not_persist_changes(authed_client, db_session):
    payload = build_dashboard_payload(cards=[{"id": "card-1", "title": "Revenue", "order": 0, "visualization_type": "bar", "size": "large", "visualization_snapshot": {"chartType": "bar", "rows": []}}])
    create_resp = await authed_client.post("/api/v1/dashboards", json=payload)
    assert create_resp.status_code == 201, create_resp.text
    dashboard_id = create_resp.json()["id"]

    invalid_update_payload = {
        "title": "Updated Revenue Overview",
        "cards": [
            {"id": "card-1", "title": "Revenue", "order": 0, "visualization_type": "bar", "size": "large", "visualization_snapshot": {"chartType": "bar", "rows": []}},
            {"id": "card-1", "title": "Revenue Duplicate", "order": 1, "visualization_type": "line", "size": "medium", "visualization_snapshot": {"chartType": "line", "rows": []}},
        ],
    }

    update_resp = await authed_client.put(f"/api/v1/dashboards/{dashboard_id}", json=invalid_update_payload)
    assert update_resp.status_code == 422, update_resp.text

    from app.models.dashboard import Dashboard
    dashboard_row = await db_session.get(Dashboard, dashboard_id)
    assert dashboard_row is not None, "Dashboard row should still exist in the session after invalid update"

    get_after_invalid = await authed_client.get(f"/api/v1/dashboards/{dashboard_id}")
    assert get_after_invalid.status_code == 200, get_after_invalid.text
    body = get_after_invalid.json()
    assert body["title"] == "Revenue Overview"
    assert len(body["cards"]) == 1
    assert body["cards"][0]["id"] == "card-1"


@pytest.mark.asyncio
async def test_dashboard_update_replaces_cards_and_delete_cascades(authed_client, db_session):
    payload = build_dashboard_payload(cards=[{"id": "card-1", "title": "Revenue", "order": 0, "visualization_type": "bar", "size": "medium", "visualization_snapshot": {"chartType": "bar", "rows": []}}])
    create_resp = await authed_client.post("/api/v1/dashboards", json=payload)
    dashboard_id = create_resp.json()["id"]

    update_payload = {
        "title": "Updated Revenue Overview",
        "description": "Refreshed",
        "cards": [
            {"id": "card-2", "title": "Updated Card", "order": 0, "visualization_type": "area", "size": "large", "visualization_snapshot": {"chartType": "area", "rows": []}},
        ],
    }
    update_resp = await authed_client.put(f"/api/v1/dashboards/{dashboard_id}", json=update_payload)
    assert update_resp.status_code == 200, update_resp.text
    updated = update_resp.json()
    assert updated["title"] == "Updated Revenue Overview"
    assert updated["description"] == "Refreshed"
    assert len(updated["cards"]) == 1
    assert updated["cards"][0]["id"] == "card-2"

    delete_resp = await authed_client.delete(f"/api/v1/dashboards/{dashboard_id}")
    assert delete_resp.status_code == 204, delete_resp.text

    get_after_delete = await authed_client.get(f"/api/v1/dashboards/{dashboard_id}")
    assert get_after_delete.status_code == 404
