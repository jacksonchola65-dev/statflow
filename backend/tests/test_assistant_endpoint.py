from __future__ import annotations

import uuid

import pytest
from app.main import create_app
from httpx import ASGITransport, AsyncClient


@pytest.mark.asyncio
async def test_assistant_requires_authentication():
    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://testserver") as client:
        response = await client.post("/api/v1/assistant/query", json={"question": "hello"})
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_assistant_disabled_state_is_safe(authed_client):
    response = await authed_client.post("/api/v1/assistant/query", json={"question": "hello"})
    assert response.status_code == 503
    assert response.json()["detail"] in {"AI_DISABLED", "AI_MISCONFIGURED"}


@pytest.mark.asyncio
async def test_assistant_rejects_client_identity_and_model_fields(authed_client):
    response = await authed_client.post(
        "/api/v1/assistant/query",
        json={"question": "hello", "user_id": str(uuid.uuid4()), "role": "ADMIN", "model": "other"},
    )
    assert response.status_code == 422
