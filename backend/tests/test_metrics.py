import re

import pytest
from app.main import create_app
from httpx import ASGITransport, AsyncClient


@pytest.mark.asyncio
async def test_metrics_endpoint_exposes_safe_request_metrics():
    app = create_app()

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        health = await client.get("/api/v1/health?secret=query-value")
        metrics = await client.get("/metrics")

    assert health.status_code == 200
    assert metrics.status_code == 200
    assert "text/plain" in metrics.headers["content-type"]
    assert "statflow_http_requests_total" in metrics.text
    assert "statflow_http_request_duration_seconds" in metrics.text
    assert 'route="/health"' in metrics.text
    assert "query-value" not in metrics.text
    assert "request_id=" not in metrics.text
    assert "secret=" not in metrics.text


@pytest.mark.asyncio
async def test_metrics_status_labels_and_dynamic_routes_are_bounded():
    app = create_app()

    @app.get("/users/{user_id}")
    async def user(user_id: str):
        return {"user_id": user_id}

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        await client.get("/users/user-123")
        metrics = await client.get("/metrics")

    assert 'route="/users/{user_id}"' in metrics.text
    assert "user-123" not in metrics.text
    assert re.search(r'status_code="200"', metrics.text)


@pytest.mark.asyncio
async def test_readiness_metric_tracks_probe_without_changing_response():
    app = create_app()

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        ready = await client.get("/api/v1/ready")
        metrics = await client.get("/metrics")

    assert ready.status_code == 200
    assert ready.json() == {
        "status": "ready",
        "service": "statflow-api",
        "database": "ready",
    }
    assert re.search(r"statflow_readiness\s+1\.0", metrics.text)
