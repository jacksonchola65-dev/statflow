import pytest
from app.core.config import settings
from app.main import create_app
from fastapi.testclient import TestClient


@pytest.fixture
def host_client(monkeypatch):
    monkeypatch.setattr(settings, "TRUSTED_HOSTS", ["pilot.onrender.com"])
    with TestClient(create_app()) as client:
        yield client


def test_allowed_trusted_host_reaches_health(host_client):
    response = host_client.get("/api/v1/health", headers={"host": "pilot.onrender.com"})
    assert response.status_code == 200


def test_disallowed_trusted_host_is_rejected(host_client):
    response = host_client.get("/api/v1/health", headers={"host": "attacker.example"})
    assert response.status_code == 400
