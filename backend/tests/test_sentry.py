from unittest.mock import MagicMock

import pytest
import sentry_sdk
from app.core.error_tracking import (
    before_send,
    capture_unexpected_exception,
    initialize_error_tracking,
)
from app.main import create_app
from fastapi import HTTPException
from httpx import ASGITransport, AsyncClient


def test_sentry_disabled_without_dsn(monkeypatch):
    init = MagicMock()
    monkeypatch.setattr(sentry_sdk, "init", init)

    assert initialize_error_tracking(None, "test", None) is False
    init.assert_not_called()


def test_sentry_initialization_is_private_and_error_only(monkeypatch):
    init = MagicMock()
    monkeypatch.setattr(sentry_sdk, "init", init)

    assert initialize_error_tracking("https://example.invalid/123", "test", "release-1") is True
    init.assert_called_once()
    options = init.call_args.kwargs
    assert options["send_default_pii"] is False
    assert options["traces_sample_rate"] == 0
    assert options["default_integrations"] is False
    assert options["environment"] == "test"
    assert options["release"] == "release-1"


def test_before_send_removes_sensitive_event_data():
    event = {
        "message": "password=topsecret",
        "request": {
            "headers": {"Authorization": "Bearer secret"},
            "cookies": {"auth": "jwt"},
            "query_string": "email=user@example.com",
            "data": "file contents",
        },
        "user": {"id": "user-123", "email": "user@example.com"},
        "extra": {"DATABASE_URL": "postgresql://user:password@host/db"},
        "breadcrumbs": [{"message": "csrf=secret"}],
        "contexts": {"statflow": {"request_id": "request-123"}},
        "exception": {"values": [{"type": "RuntimeError", "value": "topsecret"}]},
    }

    sanitized = before_send(event, {})

    assert sanitized is not None
    assert "request" not in sanitized
    assert "user" not in sanitized
    assert "extra" not in sanitized
    assert "breadcrumbs" not in sanitized
    assert sanitized["contexts"]["statflow"]["request_id"] == "request-123"
    assert sanitized["exception"]["values"][0]["value"] == "[Filtered]"
    assert "topsecret" not in str(sanitized)
    assert "DATABASE_URL" not in str(sanitized)


def test_unexpected_capture_attaches_request_id_without_tags(monkeypatch):
    scope = MagicMock()
    scope.__enter__.return_value = scope
    scope.__exit__.return_value = False
    new_scope = MagicMock(return_value=scope)
    capture = MagicMock()
    monkeypatch.setattr(sentry_sdk, "new_scope", new_scope)
    monkeypatch.setattr(sentry_sdk, "capture_exception", capture)

    error = RuntimeError("internal secret")
    capture_unexpected_exception(error, "request-123")

    scope.set_context.assert_called_once_with("statflow", {"request_id": "request-123"})
    scope.set_tag.assert_not_called()
    capture.assert_called_once_with(error)


@pytest.mark.asyncio
async def test_unexpected_exception_is_captured_once_and_response_stays_sanitized(monkeypatch):
    capture = MagicMock()
    monkeypatch.setattr("app.main.capture_unexpected_exception", capture)
    app = create_app()

    @app.get("/sentry-boom")
    async def sentry_boom():
        raise RuntimeError("DATABASE_URL=postgresql://secret")

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        response = await client.get("/sentry-boom", headers={"X-Request-ID": "request-123"})

    assert response.status_code == 500
    assert response.json() == {"detail": "Internal server error", "request_id": "request-123"}
    capture.assert_called_once()
    assert capture.call_args.args[1] == "request-123"
    assert "DATABASE_URL" not in response.text


@pytest.mark.asyncio
async def test_expected_http_exception_is_not_captured(monkeypatch):
    capture = MagicMock()
    monkeypatch.setattr("app.main.capture_unexpected_exception", capture)
    app = create_app()

    @app.get("/sentry-http-error")
    async def sentry_http_error():
        raise HTTPException(
            status_code=401,
            detail="Authentication required.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        response = await client.get("/sentry-http-error")

    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == "Bearer"
    capture.assert_not_called()


@pytest.mark.asyncio
async def test_health_readiness_and_metrics_remain_available():
    app = create_app()

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        health = await client.get("/api/v1/health")
        ready = await client.get("/api/v1/ready")
        metrics = await client.get("/metrics")

    assert health.status_code == 200
    assert health.json() == {"status": "healthy", "service": "statflow-api"}
    assert ready.status_code == 200
    assert metrics.status_code == 200
