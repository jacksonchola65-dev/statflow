import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_health_returns_200(client: AsyncClient) -> None:
    response = await client.get("/api/v1/health")
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_health_response_body(client: AsyncClient) -> None:
    response = await client.get("/api/v1/health")
    body = response.json()
    assert body["status"] == "healthy"
    assert body["service"] == "statflow-api"


@pytest.mark.asyncio
async def test_ready_returns_200_when_db_is_reachable(client: AsyncClient) -> None:
    response = await client.get("/api/v1/ready")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ready"
    assert body["service"] == "statflow-api"
    assert body["database"] == "ready"


@pytest.mark.asyncio
async def test_ready_returns_503_when_db_probe_fails(
    client: AsyncClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _BrokenConnection:
        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        async def execute(self, *_args, **_kwargs):
            raise RuntimeError("database unavailable")

    class _BrokenEngine:
        def connect(self):
            return _BrokenConnection()

    monkeypatch.setattr(
        "app.api.v1.endpoints.health.engine",
        _BrokenEngine(),
    )

    response = await client.get("/api/v1/ready")
    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "not_ready"
    assert body["service"] == "statflow-api"
    assert body["database"] == "unavailable"
    assert "database unavailable" not in response.text.lower()
    assert "runtimeerror" not in response.text.lower()
    assert "postgres" not in response.text.lower()
