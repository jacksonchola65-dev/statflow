import uuid

import pytest
from app.main import create_app
from httpx import ASGITransport, AsyncClient


@pytest.mark.asyncio
async def test_request_id_is_returned_and_propagated():
    app = create_app()

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.get(
            "/api/v1/health",
            headers={"X-Request-ID": "req-123"},
        )

    assert response.status_code == 200
    assert response.headers["X-Request-ID"] == "req-123"
    assert response.json()["status"] == "healthy"


@pytest.mark.asyncio
async def test_request_id_is_generated_when_missing():
    app = create_app()

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.get("/api/v1/health")

    request_id = response.headers["X-Request-ID"]
    assert request_id
    uuid.UUID(request_id)


@pytest.mark.asyncio
async def test_global_unhandled_exception_returns_safe_500_and_request_id():
    app = create_app()

    @app.get("/boom")
    async def boom():
        raise RuntimeError("super secret DB password = topsecret")

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.get("/boom")

    assert response.status_code == 500
    assert response.json()["detail"] == "Internal server error"
    assert "topsecret" not in response.text
    request_id = response.json()["request_id"]
    uuid.UUID(request_id)
    assert response.headers["X-Request-ID"] == request_id


@pytest.mark.asyncio
async def test_health_and_ready_endpoints_still_work():
    app = create_app()

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        health = await client.get("/api/v1/health")
        ready = await client.get("/api/v1/ready")

    assert health.status_code == 200
    assert ready.status_code == 200
