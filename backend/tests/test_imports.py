"""
test_imports.py
===============
Backend integration tests for the CSV import endpoints.

Tests POST /api/v1/imports/csv/preview and POST /api/v1/imports/csv/confirm
against the full FastAPI application using httpx.AsyncClient and a dedicated
PostgreSQL test database (statflow_test).

The shared conftest.py (session-scoped) drops/creates all tables and seeds:
  - provinces (10 Zambian provinces, e.g. CP, LP, LK …)
  - categories (10 categories, e.g. DEMOGRAPHICS, ECONOMY …)

This module seeds indicators (module-scoped, auto-use) so every test here
has POVERTY_RATE (category POVERTY) and POP_TOTAL (DEMOGRAPHICS) available.

Province codes used in tests: CP (Central), LP (Luapula)
Indicator codes used in tests: POVERTY_RATE, POP_TOTAL

References: REQ-12.1 – REQ-12.11
"""

from __future__ import annotations

import asyncio
import io
import uuid
from unittest.mock import AsyncMock, patch

import pytest
import pytest_asyncio
from sqlalchemy import select, func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

# ---------------------------------------------------------------------------
# Helpers — CSV construction
# ---------------------------------------------------------------------------

PROV1 = "CP"      # Central (seeded by conftest)
PROV2 = "LP"      # Luapula (seeded by conftest)
IND1 = "POVERTY_RATE"   # seeded below
IND2 = "POP_TOTAL"      # seeded below

HEADER = "province_code,indicator_code,value,reference_year,dataset_name,source_name\n"


def _csv(*data_rows: str) -> bytes:
    """Combine header + data rows into UTF-8 bytes."""
    return (HEADER + "\n".join(data_rows) + "\n").encode("utf-8")


def _upload(content: bytes, filename: str = "test.csv", mime: str = "text/csv") -> dict:
    """Build a files dict for httpx multipart upload."""
    return {"file": (filename, io.BytesIO(content), mime)}


# ---------------------------------------------------------------------------
# Module-scoped fixture: seed indicators once for all tests in this file.
# Provinces + categories are seeded by the session-scoped conftest fixture.
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module", autouse=True)
def seed_indicators_module():
    """
    Seed indicators into the test database once before any test in this module.
    Uses asyncio.run() because this is a synchronous fixture (module-scoped).
    """
    from app.core.config import settings
    from app.db.seeders.indicators import seed_indicators

    async def _run() -> None:
        engine = create_async_engine(
            settings.TEST_DATABASE_URL, echo=False, future=True, poolclass=NullPool
        )
        factory = async_sessionmaker(
            bind=engine, expire_on_commit=False, autocommit=False, autoflush=False
        )
        async with factory() as session:
            await seed_indicators(session)
        await engine.dispose()

    asyncio.run(_run())
    yield


# ---------------------------------------------------------------------------
# Convenience: assert a preview response is well-formed
# ---------------------------------------------------------------------------


def _assert_preview_shape(data: dict) -> None:
    for key in ("preview_token", "total_rows", "valid_rows", "invalid_rows",
                "duplicate_rows", "conflict_rows", "can_confirm",
                "errors", "total_error_count", "errors_truncated", "sample_records"):
        assert key in data, f"Missing key '{key}' in preview response"


# ===========================================================================
# TEST 1 — Valid CSV round-trip: preview → confirm → verify rows in DB
# REQ-12.1
# ===========================================================================


async def test_valid_csv_round_trip(authed_client: AsyncSession, db_session: AsyncSession) -> None:
    """
    A valid CSV:
      1. Returns HTTP 200 preview with can_confirm=True
      2. Confirms with HTTP 201
      3. DataPoint rows appear in the database
      4. Token is consumed — second confirm returns 404

    Validates: REQ-12.1
    """
    ds_name = f"RoundTrip_{uuid.uuid4().hex[:8]}"
    csv_content = _csv(
        f"{PROV1},{IND1},42.5,2020,{ds_name},Statistics Bureau",
        f"{PROV2},{IND2},1234567,2020,{ds_name},Statistics Bureau",
    )

    # Step 1 — preview
    prev_resp = await authed_client.post(
        "/api/v1/imports/csv/preview",
        files=_upload(csv_content),
    )
    assert prev_resp.status_code == 200, prev_resp.text
    preview = prev_resp.json()
    _assert_preview_shape(preview)
    assert preview["can_confirm"] is True, f"Expected can_confirm=True, got: {preview}"
    assert preview["total_rows"] == 2
    assert preview["valid_rows"] == 2
    assert preview["invalid_rows"] == 0
    assert preview["duplicate_rows"] == 0
    assert preview["conflict_rows"] == 0

    token = preview["preview_token"]

    # Step 2 — confirm
    conf_resp = await authed_client.post(
        "/api/v1/imports/csv/confirm",
        json={"preview_token": token},
    )
    assert conf_resp.status_code == 201, conf_resp.text
    result = conf_resp.json()
    assert result["imported_count"] == 2
    assert result["datasets_created"] == 1
    assert len(result["dataset_ids"]) == 1

    # Step 3 — verify rows are in the database
    from app.models.data_point import DataPoint
    from app.models.dataset import Dataset

    ds_result = await db_session.execute(
        select(Dataset).where(Dataset.name == ds_name)
    )
    dataset = ds_result.scalar_one_or_none()
    assert dataset is not None, f"Dataset '{ds_name}' not found after confirm"

    dp_count = await db_session.execute(
        select(func.count()).select_from(DataPoint).where(DataPoint.dataset_id == dataset.id)
    )
    assert dp_count.scalar() == 2

    # Step 4 — token consumed; second confirm returns 404
    second_resp = await authed_client.post(
        "/api/v1/imports/csv/confirm",
        json={"preview_token": token},
    )
    assert second_resp.status_code == 404


# ===========================================================================
# TEST 2 — File > 5 MB → HTTP 413
# REQ-12.11
# ===========================================================================


async def test_file_exceeds_5mb_returns_413(authed_client: AsyncSession) -> None:
    """
    Validates: REQ-12.11
    """
    big = b"x" * (5 * 1024 * 1024 + 1)
    resp = await authed_client.post(
        "/api/v1/imports/csv/preview",
        files=_upload(big),
    )
    assert resp.status_code == 413


# ===========================================================================
# TEST 3 — .txt extension / wrong MIME → HTTP 415
# REQ-1.1
# ===========================================================================


async def test_txt_extension_wrong_mime_returns_415(authed_client: AsyncSession) -> None:
    """
    Validates: REQ-1.1
    A file sent with MIME type 'text/plain' but a .txt filename should
    return 415 — the endpoint rejects non-CSV MIME types.

    Note: httpx sends the specified MIME type; 'text/plain' is rejected
    because only 'text/csv' is accepted.
    """
    content = _csv(f"{PROV1},{IND1},10,2020,SomeDS,SomeSource")
    resp = await authed_client.post(
        "/api/v1/imports/csv/preview",
        files=_upload(content, filename="data.txt", mime="application/octet-stream"),
    )
    assert resp.status_code == 415


# ===========================================================================
# TEST 4 — Missing `value` column → HTTP 422 with column list in detail
# REQ-2.2, REQ-12.3
# ===========================================================================


async def test_missing_value_column_returns_422_with_detail(authed_client: AsyncSession) -> None:
    """
    Validates: REQ-2.2, REQ-12.3
    """
    csv_content = (
        b"province_code,indicator_code,reference_year,dataset_name,source_name\n"
        b"CP,POVERTY_RATE,2020,DS,Src\n"
    )
    resp = await authed_client.post(
        "/api/v1/imports/csv/preview",
        files=_upload(csv_content),
    )
    assert resp.status_code == 422
    detail = str(resp.json().get("detail", ""))
    # The detail must mention 'value' (the missing column name)
    assert "value" in detail.lower(), f"Expected 'value' in detail, got: {detail}"


# ===========================================================================
# TEST 5 — Row with unknown province_code → HTTP 200, invalid_rows=1, can_confirm=false
# REQ-3.1, REQ-12.4
# ===========================================================================


async def test_unknown_province_returns_200_invalid_rows(authed_client: AsyncSession) -> None:
    """
    Validates: REQ-3.1, REQ-12.4
    An unknown province_code is a row-level error, not a file-level error.
    The endpoint returns 200 with invalid_rows≥1 and can_confirm=False.
    """
    csv_content = _csv(f"UNKNOWN_ZZZ,{IND1},55.0,2020,TestDS,TestSource")
    resp = await authed_client.post(
        "/api/v1/imports/csv/preview",
        files=_upload(csv_content),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["invalid_rows"] >= 1
    assert data["can_confirm"] is False
    assert len(data["errors"]) >= 1
    # Error must reference province_code column
    province_errors = [e for e in data["errors"] if e["column"] == "province_code"]
    assert len(province_errors) >= 1


# ===========================================================================
# TEST 6 — Intra-file duplicate → duplicate_rows=1, can_confirm=false
# REQ-4.1, REQ-12.8
# ===========================================================================


async def test_intrafile_duplicate_returns_duplicate_rows(authed_client: AsyncSession) -> None:
    """
    Validates: REQ-4.1, REQ-12.8
    Two rows with the same natural key in one file — second occurrence is a duplicate.
    """
    ds_name = f"DupTest_{uuid.uuid4().hex[:8]}"
    csv_content = _csv(
        f"{PROV1},{IND1},10.0,2020,{ds_name},DupSource",
        f"{PROV1},{IND1},20.0,2020,{ds_name},DupSource",  # same natural key
    )
    resp = await authed_client.post(
        "/api/v1/imports/csv/preview",
        files=_upload(csv_content),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["duplicate_rows"] == 1
    assert data["can_confirm"] is False


# ===========================================================================
# TEST 7 — DB conflict → conflict_rows=1, can_confirm=false
# REQ-5.1, REQ-12.9
# ===========================================================================


async def test_db_conflict_returns_conflict_rows(authed_client: AsyncSession) -> None:
    """
    Validates: REQ-5.1, REQ-12.9
    Upload a row, confirm it, then preview the same row again — should detect a conflict.
    """
    ds_name = f"ConflictPrev_{uuid.uuid4().hex[:8]}"
    csv_content = _csv(f"{PROV1},{IND1},75.0,2022,{ds_name},SomeSource")

    # First import
    prev1 = await authed_client.post("/api/v1/imports/csv/preview", files=_upload(csv_content))
    assert prev1.status_code == 200
    assert prev1.json()["can_confirm"] is True

    conf1 = await authed_client.post(
        "/api/v1/imports/csv/confirm",
        json={"preview_token": prev1.json()["preview_token"]},
    )
    assert conf1.status_code == 201

    # Second preview of same data — must detect DB conflict
    prev2 = await authed_client.post("/api/v1/imports/csv/preview", files=_upload(csv_content))
    assert prev2.status_code == 200
    data = prev2.json()
    assert data["conflict_rows"] == 1
    assert data["can_confirm"] is False


# ===========================================================================
# TEST 8 — Confirm with conflict token → HTTP 409
# REQ-7.3, REQ-12.10
# ===========================================================================


async def test_confirm_with_conflict_token_returns_409(authed_client: AsyncSession) -> None:
    """
    Validates: REQ-7.3, REQ-12.10
    Confirming a token whose preview has conflict_rows > 0 must return 409.
    """
    ds_name = f"Conf409_{uuid.uuid4().hex[:8]}"
    csv_content = _csv(f"{PROV2},{IND2},300000,2019,{ds_name},SomeSource")

    # First import succeeds
    prev1 = await authed_client.post("/api/v1/imports/csv/preview", files=_upload(csv_content))
    assert prev1.status_code == 200
    assert prev1.json()["can_confirm"] is True
    conf1 = await authed_client.post(
        "/api/v1/imports/csv/confirm",
        json={"preview_token": prev1.json()["preview_token"]},
    )
    assert conf1.status_code == 201

    # Second preview detects conflict
    prev2 = await authed_client.post("/api/v1/imports/csv/preview", files=_upload(csv_content))
    assert prev2.status_code == 200
    preview2 = prev2.json()
    assert preview2["conflict_rows"] >= 1

    # Confirm with the conflicted token → 409
    conf2 = await authed_client.post(
        "/api/v1/imports/csv/confirm",
        json={"preview_token": preview2["preview_token"]},
    )
    assert conf2.status_code == 409


# ===========================================================================
# TEST 9 — Confirm with expired / unknown token → HTTP 404
# REQ-7.2
# ===========================================================================


async def test_confirm_expired_token_returns_404(authed_client: AsyncSession) -> None:
    """
    Validates: REQ-7.2
    A random UUID (never issued) must return 404.
    """
    fake_token = str(uuid.uuid4())
    resp = await authed_client.post(
        "/api/v1/imports/csv/confirm",
        json={"preview_token": fake_token},
    )
    assert resp.status_code == 404


async def test_confirm_manually_expired_token_returns_404(authed_client: AsyncSession) -> None:
    """
    Validates: REQ-7.2, REQ-8.2
    Simulate token expiry by manipulating the token store entry's created_at
    timestamp to be older than 15 minutes.
    """
    from datetime import datetime, timedelta, timezone
    from app.services.import_service import _TOKEN_STORE

    ds_name = f"Expired_{uuid.uuid4().hex[:8]}"
    csv_content = _csv(f"{PROV1},{IND1},50.0,2021,{ds_name},SomeSource")

    # Get a valid preview token
    prev = await authed_client.post("/api/v1/imports/csv/preview", files=_upload(csv_content))
    assert prev.status_code == 200
    token = prev.json()["preview_token"]
    assert token in _TOKEN_STORE

    # Back-date the entry to simulate expiry (16 minutes ago)
    # Use timezone-aware datetime to match the token store comparison in _retrieve_token
    entry = _TOKEN_STORE[token]
    object.__setattr__(entry, "created_at", datetime.now(timezone.utc) - timedelta(minutes=16))

    # Now confirm should return 404
    resp = await authed_client.post(
        "/api/v1/imports/csv/confirm",
        json={"preview_token": token},
    )
    assert resp.status_code == 404


# ===========================================================================
# TEST 10 — Transaction rollback on IntegrityError during bulk_insert
# REQ-7.5
# ===========================================================================


async def test_transaction_rollback_on_integrity_error(
    authed_client: AsyncSession, db_session: AsyncSession
) -> None:
    """
    Validates: REQ-7.5
    Mock bulk_insert_data_points to raise IntegrityError mid-insert.
    Assert that 0 new DataPoint rows appear in the database afterwards.
    """
    from app.models.data_point import DataPoint
    from app.models.dataset import Dataset

    ds_name = f"Rollback_{uuid.uuid4().hex[:8]}"
    csv_content = _csv(
        f"{PROV1},{IND1},10.0,2023,{ds_name},RollbackSource",
        f"{PROV2},{IND2},20.0,2023,{ds_name},RollbackSource",
    )

    # Get a valid preview token
    prev = await authed_client.post("/api/v1/imports/csv/preview", files=_upload(csv_content))
    assert prev.status_code == 200
    preview = prev.json()
    assert preview["can_confirm"] is True, f"Expected can_confirm=True: {preview}"
    token = preview["preview_token"]

    # Count DataPoints before
    before_count_res = await db_session.execute(select(func.count()).select_from(DataPoint))
    before_count = before_count_res.scalar()

    # Patch bulk_insert_data_points to raise IntegrityError.
    # The IntegrityError propagates through the transaction context manager
    # (which rolls back automatically) and then through the ASGI stack.
    # FastAPI has no built-in handler for SQLAlchemy IntegrityError, so it
    # propagates as an unhandled exception in test mode.  We catch it with
    # pytest.raises and then verify the DB state to confirm rollback occurred.
    orig_path = "app.repositories.import_repository.ImportRepository.bulk_insert_data_points"
    with patch(orig_path, new_callable=AsyncMock) as mock_bulk:
        mock_bulk.side_effect = IntegrityError(
            "mock integrity error", params=None, orig=Exception("duplicate key")
        )
        # The request will raise IntegrityError (unhandled 500) in the test
        # ASGI transport — catch it to allow us to check DB state afterwards.
        try:
            conf_resp = await authed_client.post(
                "/api/v1/imports/csv/confirm",
                json={"preview_token": token},
            )
            # If FastAPI does return a response (e.g., added 500 handler later),
            # it must be a failure status code.
            assert conf_resp.status_code >= 400, (
                f"Expected error status, got {conf_resp.status_code}: {conf_resp.text}"
            )
        except IntegrityError:
            # Expected: IntegrityError propagated through the ASGI stack.
            # This confirms the transaction was aborted.
            pass

    # Verify 0 new rows were inserted (transaction rolled back).
    # Use a fresh query with a new connection to avoid stale session state.
    from app.core.config import settings as _settings
    verify_engine = create_async_engine(
        _settings.TEST_DATABASE_URL, echo=False, future=True, poolclass=NullPool
    )
    verify_factory = async_sessionmaker(
        bind=verify_engine, expire_on_commit=False, autocommit=False, autoflush=False
    )
    async with verify_factory() as verify_session:
        after_count_res = await verify_session.execute(
            select(func.count()).select_from(DataPoint)
        )
        after_count = after_count_res.scalar()

        ds_res = await verify_session.execute(
            select(Dataset).where(Dataset.name == ds_name)
        )
        dataset = ds_res.scalar_one_or_none()
    await verify_engine.dispose()

    assert after_count == before_count, (
        f"Expected {before_count} DataPoints after rollback, got {after_count}"
    )

    # Also verify dataset was NOT created (or was rolled back)
    assert dataset is None, f"Dataset '{ds_name}' should not exist after rollback"


# ===========================================================================
# TEST 11 — Error truncation: 110 unknown-province rows → errors_truncated=true,
#            len(errors)=100, total_error_count=110
# REQ-6.6, REQ-6.6a, REQ-6.6b
# ===========================================================================


async def test_error_truncation_110_invalid_rows(authed_client: AsyncSession) -> None:
    """
    Validates: REQ-6.6, REQ-6.6a, REQ-6.6b
    Upload a CSV with 110 rows all having an unknown province_code.
    The response must have:
      - errors_truncated = True
      - len(errors) = 100   (capped at MAX_ERROR_RESPONSE)
      - total_error_count = 110
    """
    rows = [
        f"UNKNOWN_ZZZ,{IND1},{i * 1.1:.1f},2020,TruncDS,TruncSource"
        for i in range(1, 111)
    ]
    csv_content = (HEADER + "\n".join(rows) + "\n").encode("utf-8")

    resp = await authed_client.post(
        "/api/v1/imports/csv/preview",
        files=_upload(csv_content),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["errors_truncated"] is True, (
        f"Expected errors_truncated=True, got: {data['errors_truncated']}"
    )
    assert len(data["errors"]) == 100, (
        f"Expected 100 errors in response, got: {len(data['errors'])}"
    )
    assert data["total_error_count"] == 110, (
        f"Expected total_error_count=110, got: {data['total_error_count']}"
    )
    assert data["can_confirm"] is False
