"""
tests/test_ingestion_config.py
===============================
Focused tests for the three ingestion limit settings added in
Milestone 1, Task 2.

Isolation strategy
------------------
All tests instantiate ``Settings(...)`` directly with explicit keyword
arguments so they are completely independent of the developer's local
.env file.  The ``_env_file`` parameter is set to ``None`` to prevent
pydantic-settings from picking up the real .env.  No environment
variables are set permanently in the process; monkeypatch is used for
the override tests so changes are rolled back after each test.

Tests cover:
- defaults load with the correct values
- valid environment overrides load correctly
- zero and negative values are rejected for each of the three fields
- non-integer environment variable values are rejected
- unrelated existing settings are unaffected
"""

from __future__ import annotations

import pytest
from app.core.config import Settings
from pydantic import ValidationError

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _settings(**overrides) -> Settings:
    """Construct a Settings instance that ignores the real .env file."""
    return Settings(_env_file=None, **overrides)


# ---------------------------------------------------------------------------
# 1. Defaults
# ---------------------------------------------------------------------------


def test_ingestion_max_file_bytes_default():
    """INGESTION_MAX_FILE_BYTES defaults to 10 MiB (10 * 1024 * 1024)."""
    s = _settings()
    assert s.INGESTION_MAX_FILE_BYTES == 10 * 1024 * 1024


def test_ingestion_max_rows_default():
    """INGESTION_MAX_ROWS defaults to 100_000."""
    s = _settings()
    assert s.INGESTION_MAX_ROWS == 100_000


def test_ingestion_max_columns_default():
    """INGESTION_MAX_COLUMNS defaults to 500."""
    s = _settings()
    assert s.INGESTION_MAX_COLUMNS == 500


# ---------------------------------------------------------------------------
# 2. Valid environment overrides
# ---------------------------------------------------------------------------


def test_ingestion_max_file_bytes_override(monkeypatch):
    """INGESTION_MAX_FILE_BYTES can be overridden via environment variable."""
    monkeypatch.setenv("INGESTION_MAX_FILE_BYTES", "5242880")  # 5 MB
    s = Settings(_env_file=None)
    assert s.INGESTION_MAX_FILE_BYTES == 5_242_880


def test_ingestion_max_rows_override(monkeypatch):
    """INGESTION_MAX_ROWS can be overridden via environment variable."""
    monkeypatch.setenv("INGESTION_MAX_ROWS", "50000")
    s = Settings(_env_file=None)
    assert s.INGESTION_MAX_ROWS == 50_000


def test_ingestion_max_columns_override(monkeypatch):
    """INGESTION_MAX_COLUMNS can be overridden via environment variable."""
    monkeypatch.setenv("INGESTION_MAX_COLUMNS", "250")
    s = Settings(_env_file=None)
    assert s.INGESTION_MAX_COLUMNS == 250


# ---------------------------------------------------------------------------
# 3. Zero values are rejected
# ---------------------------------------------------------------------------


def test_zero_file_bytes_rejected():
    """INGESTION_MAX_FILE_BYTES=0 must raise ValidationError."""
    with pytest.raises(ValidationError, match="INGESTION_MAX_FILE_BYTES"):
        _settings(INGESTION_MAX_FILE_BYTES=0)


def test_zero_rows_rejected():
    """INGESTION_MAX_ROWS=0 must raise ValidationError."""
    with pytest.raises(ValidationError, match="INGESTION_MAX_ROWS"):
        _settings(INGESTION_MAX_ROWS=0)


def test_zero_columns_rejected():
    """INGESTION_MAX_COLUMNS=0 must raise ValidationError."""
    with pytest.raises(ValidationError, match="INGESTION_MAX_COLUMNS"):
        _settings(INGESTION_MAX_COLUMNS=0)


# ---------------------------------------------------------------------------
# 4. Negative values are rejected
# ---------------------------------------------------------------------------


def test_negative_file_bytes_rejected():
    """INGESTION_MAX_FILE_BYTES=-1 must raise ValidationError."""
    with pytest.raises(ValidationError, match="INGESTION_MAX_FILE_BYTES"):
        _settings(INGESTION_MAX_FILE_BYTES=-1)


def test_negative_rows_rejected():
    """INGESTION_MAX_ROWS=-1 must raise ValidationError."""
    with pytest.raises(ValidationError, match="INGESTION_MAX_ROWS"):
        _settings(INGESTION_MAX_ROWS=-1)


def test_negative_columns_rejected():
    """INGESTION_MAX_COLUMNS=-1 must raise ValidationError."""
    with pytest.raises(ValidationError, match="INGESTION_MAX_COLUMNS"):
        _settings(INGESTION_MAX_COLUMNS=-1)


# ---------------------------------------------------------------------------
# 5. Non-integer environment variable values are rejected
# ---------------------------------------------------------------------------


def test_non_integer_file_bytes_env_rejected(monkeypatch):
    """INGESTION_MAX_FILE_BYTES='ten_mb' (non-integer) must fail validation."""
    monkeypatch.setenv("INGESTION_MAX_FILE_BYTES", "ten_mb")
    with pytest.raises((ValidationError, ValueError)):
        Settings(_env_file=None)


def test_non_integer_rows_env_rejected(monkeypatch):
    """INGESTION_MAX_ROWS='many' (non-integer) must fail validation."""
    monkeypatch.setenv("INGESTION_MAX_ROWS", "many")
    with pytest.raises((ValidationError, ValueError)):
        Settings(_env_file=None)


def test_non_integer_columns_env_rejected(monkeypatch):
    """INGESTION_MAX_COLUMNS='lots' (non-integer) must fail validation."""
    monkeypatch.setenv("INGESTION_MAX_COLUMNS", "lots")
    with pytest.raises((ValidationError, ValueError)):
        Settings(_env_file=None)


# ---------------------------------------------------------------------------
# 6. Unrelated existing settings are unaffected
# ---------------------------------------------------------------------------


def test_unrelated_settings_load_correctly():
    """Other settings fields are unchanged after adding ingestion limits."""
    s = _settings()
    assert s.APP_NAME == "StatFlow API"
    assert s.API_V1_PREFIX == "/api/v1"
    assert s.JWT_ALGORITHM == "HS256"
    assert s.ACCESS_TOKEN_EXPIRE_MINUTES == 60
    assert s.COOKIE_SAMESITE == "lax"
    assert s.CSRF_HEADER_NAME == "X-CSRF-Token"


# ---------------------------------------------------------------------------
# 7. Settings are accessible via the shared singleton
# ---------------------------------------------------------------------------


def test_singleton_exposes_ingestion_settings():
    """The shared ``settings`` object exposes all three ingestion fields."""
    from app.core.config import settings

    assert hasattr(settings, "INGESTION_MAX_FILE_BYTES")
    assert hasattr(settings, "INGESTION_MAX_ROWS")
    assert hasattr(settings, "INGESTION_MAX_COLUMNS")
    assert isinstance(settings.INGESTION_MAX_FILE_BYTES, int)
    assert isinstance(settings.INGESTION_MAX_ROWS, int)
    assert isinstance(settings.INGESTION_MAX_COLUMNS, int)


def _production_settings(**overrides) -> Settings:
    values = {
        "ENVIRONMENT": "production",
        "DATABASE_URL": "postgresql+asyncpg://app:password@db.example/statflow",
        "JWT_SECRET_KEY": "x" * 32,
        "ADMIN_PASSWORD": "a-strong-production-password",
        "COOKIE_SECURE": True,
        "CORS_ORIGINS": ["https://app.statflow.example"],
        "TRUSTED_HOSTS": ["app.statflow.example"],
    }
    values.update(overrides)
    return _settings(**values)


def test_production_rejects_default_admin_password():
    with pytest.raises(ValidationError, match="ADMIN_PASSWORD") as error:
        _production_settings(ADMIN_PASSWORD="ChangeMe123!")
    assert "ChangeMe123!" not in str(error.value)


def test_production_rejects_insecure_cookie_setting():
    with pytest.raises(ValidationError, match="COOKIE_SECURE"):
        _production_settings(COOKIE_SECURE=False)


@pytest.mark.parametrize(
    "origin",
    [
        "http://localhost",
        "https://localhost:5173",
        "http://127.0.0.1",
        "https://127.0.0.1:8443",
    ],
)
def test_production_rejects_loopback_cors_origins(origin):
    with pytest.raises(ValidationError, match="CORS_ORIGINS"):
        _production_settings(CORS_ORIGINS=[origin])


def test_production_rejects_wildcard_cors_origin():
    with pytest.raises(ValidationError, match="CORS_ORIGINS"):
        _production_settings(CORS_ORIGINS=["*"])


def test_production_accepts_valid_origin_and_secure_settings():
    settings = _production_settings()
    assert settings.ENVIRONMENT == "production"
    assert settings.COOKIE_SECURE is True
    assert settings.CORS_ORIGINS == ["https://app.statflow.example"]


def test_hostname_containing_localhost_is_not_loopback():
    settings = _production_settings(CORS_ORIGINS=["https://localhost.example.com"])
    assert settings.CORS_ORIGINS == ["https://localhost.example.com"]


def test_development_defaults_remain_allowed():
    settings = _settings()
    assert settings.COOKIE_SECURE is False
    assert settings.CORS_ORIGINS == ["http://localhost:5173"]
    assert settings.ADMIN_PASSWORD == "ChangeMe123!"


def test_supported_test_environment_is_accepted():
    assert _settings(ENVIRONMENT="test").ENVIRONMENT == "test"


def test_unsupported_environment_is_rejected():
    with pytest.raises(ValidationError, match="ENVIRONMENT"):
        _settings(ENVIRONMENT="qa")


def test_production_rejects_sqlite_database_url():
    with pytest.raises(ValidationError, match="DATABASE_URL"):
        _production_settings(DATABASE_URL="sqlite:///statflow.db")


def test_staging_requires_explicit_production_like_configuration():
    staging = _settings(
        ENVIRONMENT="staging",
        DATABASE_URL="postgresql+asyncpg://app:password@staging-db.example/statflow",
        JWT_SECRET_KEY="s" * 32,
        ADMIN_PASSWORD="staging-bootstrap-password",
        COOKIE_SECURE=True,
        CORS_ORIGINS=["https://staging.statflow.example"],
        TRUSTED_HOSTS=["staging.statflow.example"],
    )
    assert staging.ENVIRONMENT == "staging"


@pytest.mark.parametrize("field", ["DATABASE_URL", "JWT_SECRET_KEY", "ADMIN_PASSWORD"])
def test_staging_rejects_missing_required_secret_or_database(field):
    values = {
        "DATABASE_URL": "postgresql+asyncpg://app:password@db.example/statflow",
        "JWT_SECRET_KEY": "s" * 32,
        "ADMIN_PASSWORD": "staging-bootstrap-password",
        "COOKIE_SECURE": True,
        "CORS_ORIGINS": ["https://staging.statflow.example"],
        "TRUSTED_HOSTS": ["staging.statflow.example"],
    }
    values[field] = ""
    with pytest.raises(ValidationError, match=field):
        _settings(ENVIRONMENT="staging", **values)


def test_production_rejects_default_database_url():
    with pytest.raises(ValidationError, match="DATABASE_URL"):
        _settings(
            ENVIRONMENT="production",
            JWT_SECRET_KEY="x" * 32,
            ADMIN_PASSWORD="strong-production-password",
            COOKIE_SECURE=True,
            CORS_ORIGINS=["https://app.statflow.example"],
            TRUSTED_HOSTS=["app.statflow.example"],
        )


@pytest.mark.parametrize("secret", ["change-me", "secret", "your-secret-key", "x" * 31])
def test_production_rejects_weak_or_placeholder_jwt_secret(secret):
    with pytest.raises(ValidationError, match="JWT_SECRET_KEY"):
        _production_settings(JWT_SECRET_KEY=secret)


@pytest.mark.parametrize("samesite", ["invalid", "None", "strict-ish"])
def test_invalid_samesite_is_rejected(samesite):
    with pytest.raises(ValidationError, match="COOKIE_SAMESITE"):
        _settings(COOKIE_SAMESITE=samesite)


def test_production_rejects_wildcard_trusted_hosts():
    with pytest.raises(ValidationError, match="TRUSTED_HOSTS"):
        _production_settings(TRUSTED_HOSTS=["*"])


def test_validation_errors_do_not_include_secret_values():
    secret = "a-unique-invalid-secret-value"
    with pytest.raises(ValidationError) as error:
        _production_settings(JWT_SECRET_KEY=secret)
    assert secret not in str(error.value)
