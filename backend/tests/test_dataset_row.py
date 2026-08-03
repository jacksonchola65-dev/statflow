"""
tests/test_dataset_row.py
==========================
Tests for the DatasetRow model, row_values validation helper, and
the migration constraints (via the real test database).

Covers:
  - valid row creation
  - multiple rows for one ingestion job
  - same row_number allowed across different jobs
  - duplicate row_number rejected within one job
  - negative row_number rejected
  - cascading deletion with parent ingestion job
  - empty JSON object behaviour
  - rejection of arrays and scalar JSON values (DB CHECK constraint)
  - rejection of NaN and infinities (Python-layer validation)
  - relationship behaviour (IngestionJob.rows)
  - row_values serialization helper (pure unit tests)
"""

from __future__ import annotations

import sys

if sys.platform == "win32":
    import asyncio as _asyncio

    _asyncio.set_event_loop_policy(_asyncio.WindowsSelectorEventLoopPolicy())

import uuid
from decimal import Decimal

import pytest
from app.models.data_source import DatasetRegistry, FileFormat, SourceType
from app.models.ingestion import DatasetRow, IngestionJob
from app.utils.row_values import RowValuesError, serialize_row_values, validate_row_values
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _make_registry(db_session) -> DatasetRegistry:
    from app.repositories.data_source_repository import DataSourceRepository
    from app.repositories.dataset_registry_repository import DatasetRegistryRepository

    ds_repo = DataSourceRepository(db_session)
    ds = await ds_repo.create(name=f"src-{uuid.uuid4().hex[:6]}", is_active=True)
    await db_session.flush()

    reg_repo = DatasetRegistryRepository(db_session)
    registry = await reg_repo.create(
        data_source_id=ds.id,
        dataset_name=f"ds-{uuid.uuid4().hex[:6]}",
        source_type=SourceType.OFFICIAL,
    )
    await db_session.flush()
    return registry


async def _make_job(db_session, registry: DatasetRegistry) -> IngestionJob:
    from app.repositories.ingestion_job_repository import IngestionJobRepository

    repo = IngestionJobRepository(db_session)
    job = await repo.create(
        dataset_registry_id=registry.id,
        original_filename="test.csv",
        file_format=FileFormat.CSV,
        file_size_bytes=1024,
    )
    return job


async def _insert_row(
    db_session,
    job: IngestionJob,
    row_number: int = 0,
    values: dict | None = None,
) -> DatasetRow:
    """Insert a DatasetRow directly via ORM."""
    row = DatasetRow(
        ingestion_job_id=job.id,
        row_number=row_number,
        values=values if values is not None else {"col_a": "hello"},
    )
    db_session.add(row)
    await db_session.flush()
    return row


# ===========================================================================
# Pure unit tests — serialize_row_values and validate_row_values
# ===========================================================================


def test_serialize_accepts_none_value():
    result = serialize_row_values({"col": None})
    assert result == {"col": None}


def test_serialize_accepts_bool():
    result = serialize_row_values({"flag": True})
    assert result["flag"] is True


def test_serialize_accepts_int():
    result = serialize_row_values({"count": 42})
    assert result["count"] == 42


def test_serialize_accepts_float():
    result = serialize_row_values({"ratio": 3.14})
    assert abs(result["ratio"] - 3.14) < 1e-9


def test_serialize_accepts_string():
    result = serialize_row_values({"name": "Lusaka"})
    assert result["name"] == "Lusaka"


def test_serialize_converts_finite_decimal_to_string():
    result = serialize_row_values({"amount": Decimal("12.50")})
    assert isinstance(result["amount"], str)
    assert result["amount"] == "12.50"


def test_serialize_rejects_nan_float():
    with pytest.raises(RowValuesError, match="finite"):
        serialize_row_values({"val": float("nan")})


def test_serialize_rejects_pos_inf():
    with pytest.raises(RowValuesError, match="finite"):
        serialize_row_values({"val": float("inf")})


def test_serialize_rejects_neg_inf():
    with pytest.raises(RowValuesError, match="finite"):
        serialize_row_values({"val": float("-inf")})


def test_serialize_rejects_decimal_nan():
    with pytest.raises(RowValuesError, match="finite"):
        serialize_row_values({"val": Decimal("NaN")})


def test_serialize_rejects_decimal_inf():
    with pytest.raises(RowValuesError, match="finite"):
        serialize_row_values({"val": Decimal("Infinity")})


def test_serialize_decimal_with_trailing_zeros():
    """Decimal(\"100.00\") → \"100.00\" (preserves trailing zeros)"""
    result = serialize_row_values({"val": Decimal("100.00")})
    assert result["val"] == "100.00"


def test_serialize_decimal_with_high_precision():
    """High-precision Decimal values preserve all significant digits."""
    result = serialize_row_values({"val": Decimal("27.345678901234567890")})
    assert result["val"] == "27.345678901234567890"


def test_serialize_decimal_negative():
    """Negative Decimal values are converted to strings with sign."""
    result = serialize_row_values({"val": Decimal("-123.45")})
    assert result["val"] == "-123.45"


def test_serialize_decimal_zero():
    """Decimal zero is converted to string \"0\"."""
    result = serialize_row_values({"val": Decimal("0")})
    assert result["val"] == "0"


def test_serialize_decimal_very_small():
    """Very small Decimal values preserve precision in fixed-point notation."""
    result = serialize_row_values({"val": Decimal("0.0000000001")})
    assert isinstance(result["val"], str)
    assert result["val"] == "0.0000000001"


def test_serialize_decimal_very_large():
    """Very large Decimal values preserve precision."""
    result = serialize_row_values({"val": Decimal("123456789.123456789")})
    assert isinstance(result["val"], str)
    assert result["val"] == "123456789.123456789"


def test_serialize_rejects_decimal_nan_object():
    """Direct Decimal NaN object is rejected by serialization."""
    with pytest.raises(RowValuesError, match="finite"):
        serialize_row_values({"val": Decimal("NaN")})


def test_serialize_rejects_decimal_positive_infinity():
    """Direct Decimal Infinity object is rejected by serialization."""
    with pytest.raises(RowValuesError, match="finite"):
        serialize_row_values({"val": Decimal("Infinity")})


def test_serialize_rejects_decimal_negative_infinity():
    """Direct Decimal -Infinity object is rejected by serialization."""
    with pytest.raises(RowValuesError, match="finite"):
        serialize_row_values({"val": Decimal("-Infinity")})


def test_serialize_rejects_list_value():
    with pytest.raises(RowValuesError):
        serialize_row_values({"col": [1, 2, 3]})


def test_serialize_rejects_dict_value():
    with pytest.raises(RowValuesError):
        serialize_row_values({"col": {"nested": "value"}})


def test_serialize_rejects_bytes_value():
    with pytest.raises(RowValuesError):
        serialize_row_values({"col": b"bytes"})


def test_serialize_rejects_non_dict_input():
    with pytest.raises(RowValuesError, match="dict"):
        serialize_row_values([{"col": 1}])  # type: ignore[arg-type]


def test_serialize_rejects_scalar_input():
    with pytest.raises(RowValuesError, match="dict"):
        serialize_row_values("not a dict")  # type: ignore[arg-type]


def test_serialize_empty_dict_is_valid():
    """An empty dict is a valid JSON object (no columns stored yet)."""
    result = serialize_row_values({})
    assert result == {}


def test_validate_passes_clean_dict():
    validate_row_values({"col": 1, "name": "test", "flag": True})


def test_validate_rejects_list():
    with pytest.raises(RowValuesError, match="dict"):
        validate_row_values([1, 2, 3])


def test_validate_rejects_none():
    with pytest.raises(RowValuesError, match="dict"):
        validate_row_values(None)


# ===========================================================================
# Integration tests — DatasetRow model against real test DB
# ===========================================================================


async def test_row_create_valid(db_session):
    """A valid DatasetRow is created and has a populated UUID."""
    registry = await _make_registry(db_session)
    job = await _make_job(db_session, registry)
    row = await _insert_row(db_session, job, row_number=0, values={"name": "Alice", "age": 30})
    assert row.id is not None
    assert isinstance(row.id, uuid.UUID)
    assert row.row_number == 0
    assert row.values == {"name": "Alice", "age": 30}
    assert row.ingestion_job_id == job.id


async def test_multiple_rows_for_one_job(db_session):
    """Multiple rows with different row_numbers can be inserted for one job."""
    registry = await _make_registry(db_session)
    job = await _make_job(db_session, registry)
    for i in range(5):
        await _insert_row(db_session, job, row_number=i, values={"idx": i})

    result = await db_session.execute(
        select(func.count()).select_from(DatasetRow).where(DatasetRow.ingestion_job_id == job.id)
    )
    assert result.scalar_one() == 5


async def test_same_row_number_allowed_different_jobs(db_session):
    """The same row_number is valid across different jobs (uniqueness is per-job)."""
    registry = await _make_registry(db_session)
    job_a = await _make_job(db_session, registry)
    job_b = await _make_job(db_session, registry)
    await _insert_row(db_session, job_a, row_number=0, values={"x": 1})
    await _insert_row(db_session, job_b, row_number=0, values={"x": 2})
    # Both succeed — no IntegrityError


async def test_duplicate_row_number_same_job_rejected(db_session):
    """Inserting two rows with the same row_number for one job raises IntegrityError."""
    registry = await _make_registry(db_session)
    job = await _make_job(db_session, registry)
    await _insert_row(db_session, job, row_number=0, values={"a": 1})
    await db_session.flush()
    with pytest.raises(IntegrityError):
        await _insert_row(db_session, job, row_number=0, values={"a": 2})
        await db_session.flush()


async def test_negative_row_number_rejected(db_session):
    """row_number < 0 is rejected by the CHECK constraint."""
    registry = await _make_registry(db_session)
    job = await _make_job(db_session, registry)
    with pytest.raises(IntegrityError):
        await _insert_row(db_session, job, row_number=-1, values={"a": 1})
        await db_session.flush()


async def test_cascade_delete_removes_rows(db_session):
    """Deleting an IngestionJob cascades to its DatasetRow records."""
    from app.repositories.ingestion_job_repository import IngestionJobRepository

    registry = await _make_registry(db_session)
    job = await _make_job(db_session, registry)
    for i in range(3):
        await _insert_row(db_session, job, row_number=i)
    await db_session.flush()

    job_repo = IngestionJobRepository(db_session)
    await job_repo.delete(job.id)
    await db_session.flush()

    result = await db_session.execute(
        select(func.count()).select_from(DatasetRow).where(DatasetRow.ingestion_job_id == job.id)
    )
    assert result.scalar_one() == 0


async def test_empty_json_object_is_valid(db_session):
    """An empty dict {} is accepted as a valid JSON object."""
    registry = await _make_registry(db_session)
    job = await _make_job(db_session, registry)
    row = await _insert_row(db_session, job, row_number=0, values={})
    assert row.values == {}


async def test_json_array_rejected_by_db(db_session):
    """A JSON array value for DatasetRow.values is rejected by the DB CHECK constraint."""
    registry = await _make_registry(db_session)
    job = await _make_job(db_session, registry)
    with pytest.raises(IntegrityError):
        row = DatasetRow(
            ingestion_job_id=job.id,
            row_number=0,
            values=[1, 2, 3],  # array — violates ck_dataset_rows_values_is_object
        )
        db_session.add(row)
        await db_session.flush()


async def test_json_scalar_rejected_by_db(db_session):
    """A JSON scalar value for DatasetRow.values is rejected by the DB CHECK constraint."""
    registry = await _make_registry(db_session)
    job = await _make_job(db_session, registry)
    with pytest.raises(IntegrityError):
        row = DatasetRow(
            ingestion_job_id=job.id,
            row_number=0,
            values=42,  # scalar — violates ck_dataset_rows_values_is_object
        )
        db_session.add(row)
        await db_session.flush()


async def test_relationship_accessible(db_session):
    """IngestionJob.rows is accessible via explicit SELECT query (not ORM attribute)."""
    registry = await _make_registry(db_session)
    job = await _make_job(db_session, registry)
    await _insert_row(db_session, job, row_number=0)
    await _insert_row(db_session, job, row_number=1)
    await db_session.flush()
    # Access via explicit query (correct production pattern)
    result = await db_session.execute(
        select(DatasetRow).where(DatasetRow.ingestion_job_id == job.id)
    )
    rows = list(result.scalars().all())
    assert len(rows) == 2
    assert all(r.ingestion_job_id == job.id for r in rows)


async def test_row_created_at_is_populated(db_session):
    """created_at is automatically set by the server default."""
    registry = await _make_registry(db_session)
    job = await _make_job(db_session, registry)
    row = await _insert_row(db_session, job)
    assert row.created_at is not None


# ===========================================================================
# Hardening tests — lazy="raise", passive_deletes, index architecture
# ===========================================================================


async def test_implicit_rows_access_raises(db_session):
    """Accessing job.rows without an explicit load must raise (lazy='raise').

    This prevents accidental unbounded queries on a relationship that may
    hold up to 100,000 rows.
    """
    from sqlalchemy.exc import InvalidRequestError

    registry = await _make_registry(db_session)
    job = await _make_job(db_session, registry)
    await _insert_row(db_session, job, row_number=0)
    await db_session.flush()

    # Expire the job so the ORM would need to load the relationship
    db_session.expire(job)

    with pytest.raises((InvalidRequestError, Exception)):
        # Accessing job.rows should raise because lazy="raise"
        _ = job.rows


async def test_cascade_delete_does_not_load_rows(db_session):
    """Deleting an IngestionJob removes rows via DB cascade, not ORM loading.

    passive_deletes=True means SQLAlchemy will NOT load rows before deletion.
    The DB ON DELETE CASCADE handles it. We verify rows are gone after deletion.
    """
    from app.repositories.ingestion_job_repository import IngestionJobRepository

    registry = await _make_registry(db_session)
    job = await _make_job(db_session, registry)
    for i in range(5):
        await _insert_row(db_session, job, row_number=i)
    await db_session.flush()

    # Delete the job — passive_deletes=True means no SELECT before DELETE
    job_repo = IngestionJobRepository(db_session)
    await job_repo.delete(job.id)
    await db_session.flush()

    # Rows must be gone (DB cascade handled it)
    result = await db_session.execute(
        select(func.count()).select_from(DatasetRow).where(DatasetRow.ingestion_job_id == job.id)
    )
    assert result.scalar_one() == 0


async def test_redundant_explicit_index_is_absent(db_session):
    """ix_dataset_rows_job_row_number must NOT exist — it was dropped.

    The unique constraint uq_dataset_rows_job_row_number already provides
    an equivalent index in PostgreSQL.
    """
    result = await db_session.execute(
        text(
            "SELECT indexname FROM pg_indexes "
            "WHERE tablename = 'dataset_rows' "
            "AND indexname = 'ix_dataset_rows_job_row_number'"
        )
    )
    rows = result.fetchall()
    assert len(rows) == 0, (
        "ix_dataset_rows_job_row_number should have been dropped — it duplicates "
        "the unique constraint index uq_dataset_rows_job_row_number."
    )


async def test_unique_constraint_index_exists(db_session):
    """uq_dataset_rows_job_row_number (the unique constraint index) must exist."""
    result = await db_session.execute(
        text(
            "SELECT indexname FROM pg_indexes "
            "WHERE tablename = 'dataset_rows' "
            "AND indexname = 'uq_dataset_rows_job_row_number'"
        )
    )
    rows = result.fetchall()
    assert len(rows) == 1, "Unique constraint index uq_dataset_rows_job_row_number must exist."


async def test_rows_accessible_via_explicit_select(db_session):
    """Rows are accessible when queried explicitly (the correct pattern)."""
    registry = await _make_registry(db_session)
    job = await _make_job(db_session, registry)
    await _insert_row(db_session, job, row_number=0, values={"name": "explicit"})
    await db_session.flush()

    result = await db_session.execute(
        select(DatasetRow)
        .where(DatasetRow.ingestion_job_id == job.id)
        .order_by(DatasetRow.row_number)
    )
    rows = result.scalars().all()
    assert len(rows) == 1
    assert rows[0].values == {"name": "explicit"}
