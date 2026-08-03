"""
tests/test_mapping_execution_service.py
========================================
Focused unit tests for MappingExecutionService — Phase 1 (token retrieval).

Tests:
  1. Valid token, correct owner  → returns CachedInspection
  2. Valid token, wrong owner    → raises InspectionOwnershipError
  3. Expired token               → raises InspectionNotFoundError
  4. Non-existent token          → raises InspectionNotFoundError
  5. service.get_inspection does NOT call session methods (pure lookup)
"""

from __future__ import annotations

import sys
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

if sys.platform == "win32":
    import asyncio as _asyncio

    _asyncio.set_event_loop_policy(_asyncio.WindowsSelectorEventLoopPolicy())

from app.services.file_inspection_service import (
    _INSPECTION_STORE,
    CachedInspection,
    _InspectionTokenEntry,
)
from app.services.mapping_execution_service import (
    InspectionNotFoundError,
    InspectionOwnershipError,
    MappingExecutionService,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_cached(owner_id: uuid.UUID, token: str = "") -> CachedInspection:
    """Build a minimal CachedInspection for testing."""
    return CachedInspection(
        inspection_token=token or str(uuid.uuid4()),
        filename="orders.csv",
        source_format="csv",
        headers=["order_id", "region", "revenue"],
        columns=[],
        direct_schema_match=False,
        suggested_mappings=[],
        warnings=[],
        owner_id=owner_id,
    )


def _insert_token(
    token: str,
    owner_id: uuid.UUID,
    age_minutes: float = 0,
) -> CachedInspection:
    """
    Directly insert a token into the inspection store, optionally back-dated.
    Returns the CachedInspection that was stored.
    """
    cached = _make_cached(owner_id, token=token)
    created_at = datetime.now(timezone.utc) - timedelta(minutes=age_minutes)
    _INSPECTION_STORE[token] = _InspectionTokenEntry(
        payload=cached,
        created_at=created_at,
    )
    return cached


def _stub_session() -> MagicMock:
    """Return a MagicMock that stands in for AsyncSession (not called in Phase 1)."""
    return MagicMock()


# ---------------------------------------------------------------------------
# Fixture: clean up test tokens after each test
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def cleanup_tokens():
    """Remove any tokens added by tests so the store stays clean."""
    inserted: list[str] = []
    _original_insert = _insert_token

    yield inserted  # tests may append token strings here to track them

    for tok in inserted:
        _INSPECTION_STORE.pop(tok, None)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_get_inspection_returns_cached_for_valid_owner(cleanup_tokens):
    """Valid token + correct owner → CachedInspection returned."""
    owner_id = uuid.uuid4()
    token = str(uuid.uuid4())
    cleanup_tokens.append(token)

    expected = _insert_token(token, owner_id, age_minutes=0)
    svc = MappingExecutionService(session=_stub_session())

    result = svc.get_inspection(token, owner_id)

    assert result is expected
    assert result.owner_id == owner_id
    assert result.filename == "orders.csv"
    assert result.direct_schema_match is False


def test_get_inspection_raises_ownership_error_for_wrong_owner(cleanup_tokens):
    """Valid token + different owner → InspectionOwnershipError."""
    real_owner = uuid.uuid4()
    attacker = uuid.uuid4()
    token = str(uuid.uuid4())
    cleanup_tokens.append(token)

    _insert_token(token, real_owner, age_minutes=0)
    svc = MappingExecutionService(session=_stub_session())

    with pytest.raises(InspectionOwnershipError):
        svc.get_inspection(token, attacker)


def test_get_inspection_raises_not_found_for_expired_token(cleanup_tokens):
    """Token older than 15 minutes → InspectionNotFoundError."""
    owner_id = uuid.uuid4()
    token = str(uuid.uuid4())
    cleanup_tokens.append(token)

    # Age it by 16 minutes — past the 15-minute TTL
    _insert_token(token, owner_id, age_minutes=16)
    svc = MappingExecutionService(session=_stub_session())

    with pytest.raises(InspectionNotFoundError):
        svc.get_inspection(token, owner_id)


def test_get_inspection_raises_not_found_for_nonexistent_token():
    """Token that was never issued → InspectionNotFoundError."""
    owner_id = uuid.uuid4()
    bogus_token = str(uuid.uuid4())  # never inserted
    svc = MappingExecutionService(session=_stub_session())

    with pytest.raises(InspectionNotFoundError):
        svc.get_inspection(bogus_token, owner_id)


def test_get_inspection_does_not_call_session(cleanup_tokens):
    """
    Phase 1 uses only the in-process token store.
    The SQLAlchemy session must not be touched.
    """
    owner_id = uuid.uuid4()
    token = str(uuid.uuid4())
    cleanup_tokens.append(token)

    _insert_token(token, owner_id, age_minutes=0)
    mock_session = MagicMock()
    svc = MappingExecutionService(session=mock_session)

    svc.get_inspection(token, owner_id)

    # No SQLAlchemy session methods should have been called
    mock_session.execute.assert_not_called()
    mock_session.flush.assert_not_called()
    mock_session.commit.assert_not_called()


def test_expired_token_is_evicted_from_store(cleanup_tokens):
    """After an expired token raises, it should be removed from the store."""
    owner_id = uuid.uuid4()
    token = str(uuid.uuid4())
    cleanup_tokens.append(token)

    _insert_token(token, owner_id, age_minutes=16)
    svc = MappingExecutionService(session=_stub_session())

    with pytest.raises(InspectionNotFoundError):
        svc.get_inspection(token, owner_id)

    # Token should have been evicted by the store's lazy eviction
    assert token not in _INSPECTION_STORE


def test_token_still_valid_just_before_expiry(cleanup_tokens):
    """A token aged 14 minutes 59 seconds is still valid (< 15 min TTL)."""
    owner_id = uuid.uuid4()
    token = str(uuid.uuid4())
    cleanup_tokens.append(token)

    # Age it by ~14.98 minutes — within the TTL
    _insert_token(token, owner_id, age_minutes=14.98)
    svc = MappingExecutionService(session=_stub_session())

    result = svc.get_inspection(token, owner_id)
    assert result.owner_id == owner_id
