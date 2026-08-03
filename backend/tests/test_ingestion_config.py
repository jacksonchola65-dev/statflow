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
