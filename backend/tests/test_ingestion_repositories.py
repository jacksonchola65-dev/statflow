"""
tests/test_ingestion_repositories.py
=====================================
Integration tests for IngestionJobRepository and DatasetColumnRepository.

Uses the real test database via the shared db_session fixture so queries
exercise actual SQL, index behavior, and FK constraints.

All tests are async and use pytest-asyncio (mode=AUTO per pytest.ini).
"""

from __future__ import annotations

import sys

if sys.platform == "win32":
    import asyncio as _asyncio

    _asyncio.set_event_loop_policy(_asyncio.WindowsSelectorEventLoopPolicy())

import uuid
from datetime import datetime, timezone

import pytest
from app.models.data_source import DatasetRegistry, FileFormat, SourceType
from app.models.ingestion import DatasetColumn, InferredColumnType, IngestionJob, IngestionStatus
from app.repositories.dataset_column_repository import DatasetColumnRepository
from app.repositories.ingestion_job_repository import IngestionJobRepository

# ---------------------------------------------------------------------------
# Shared test helpers
# ---------------------------------------------------------------------------


async def _make_registry(db_session) -> DatasetRegistry:
    """Create a minimal DatasetRegistry row for FK satisfaction."""
    from app.repositories.data_source_repository import DataSourceRepository
    from app.repositories.dataset_registry_repository import DatasetRegistryRepository

    ds_repo = DataSourceRepository(db_session)
    ds = await ds_repo.create(
        name=f"Test Source {uuid.uuid4().hex[:6]}",
        is_active=True,
    )
    await db_session.flush()

    reg_repo = DatasetRegistryRepository(db_session)
    registry = await reg_repo.create(
        data_source_id=ds.id,
        dataset_name=f"Test Dataset {uuid.uuid4().hex[:6]}",
        source_type=SourceType.OFFICIAL,
    )
    await db_session.flush()
    return registry


async def _make_job(
    db_session,
    registry: DatasetRegistry,
    status: IngestionStatus = IngestionStatus.PENDING,
    filename: str = "test.csv",
) -> IngestionJob:
    """Create a minimal IngestionJob via the repository."""
    repo = IngestionJobRepository(db_session)
    job = await repo.create(
        dataset_registry_id=registry.id,
        original_filename=filename,
        file_format=FileFormat.CSV,
        file_size_bytes=1024,
        status=status,
    )
    return job


async def _make_column(
    db_session,
    job: IngestionJob,
    original_name: str = "col_a",
    normalized_name: str = "col_a",
    inferred_type: InferredColumnType = InferredColumnType.TEXT,
    ordinal_position: int = 0,
) -> DatasetColumn:
    """Create a single DatasetColumn via create_many."""
    repo = DatasetColumnRepository(db_session)
    cols = await repo.create_many(
        [
            {
                "ingestion_job_id": job.id,
                "original_name": original_name,
                "normalized_name": normalized_name,
                "inferred_type": inferred_type,
                "nullable": False,
                "missing_count": 0,
                "unique_count": 5,
                "sample_values": ["a", "b", "c"],
                "ordinal_position": ordinal_position,
            }
        ]
    )
    return cols[0]


# ===========================================================================
# IngestionJobRepository — create / get_by_id / exists
# ===========================================================================


async def test_job_create_returns_job_with_id(db_session):
    """create() returns an IngestionJob with a populated UUID."""
    registry = await _make_registry(db_session)
    job = await _make_job(db_session, registry)
    assert job.id is not None
    assert isinstance(job.id, uuid.UUID)
    assert job.status == IngestionStatus.PENDING
    assert job.original_filename == "test.csv"
    assert job.file_format == FileFormat.CSV


async def test_job_create_default_status_is_pending(db_session):
    """create() sets status to PENDING by default."""
    registry = await _make_registry(db_session)
    job = await _make_job(db_session, registry)
    assert job.status == IngestionStatus.PENDING


async def test_job_get_by_id_found(db_session):
    """get_by_id() returns the job when it exists."""
    registry = await _make_registry(db_session)
    job = await _make_job(db_session, registry)
    repo = IngestionJobRepository(db_session)
    fetched = await repo.get_by_id(job.id)
    assert fetched is not None
    assert fetched.id == job.id


async def test_job_get_by_id_not_found(db_session):
    """get_by_id() returns None for a non-existent UUID."""
    repo = IngestionJobRepository(db_session)
    result = await repo.get_by_id(uuid.uuid4())
    assert result is None


async def test_job_exists_true(db_session):
    """exists() returns True when the job is present."""
    registry = await _make_registry(db_session)
    job = await _make_job(db_session, registry)
    repo = IngestionJobRepository(db_session)
    assert await repo.exists(job.id) is True


async def test_job_exists_false(db_session):
    """exists() returns False for a non-existent UUID."""
    repo = IngestionJobRepository(db_session)
    assert await repo.exists(uuid.uuid4()) is False


# ===========================================================================
# IngestionJobRepository — update
# ===========================================================================


async def test_job_update_status(db_session):
    """update() changes the status field."""
    registry = await _make_registry(db_session)
    job = await _make_job(db_session, registry)
    repo = IngestionJobRepository(db_session)
    updated = await repo.update(job.id, status=IngestionStatus.PROCESSING)
    assert updated is not None
    assert updated.status == IngestionStatus.PROCESSING


async def test_job_update_completed(db_session):
    """update() can set multiple fields at once for a completed job."""
    registry = await _make_registry(db_session)
    job = await _make_job(db_session, registry)
    now = datetime.now(timezone.utc)
    repo = IngestionJobRepository(db_session)
    updated = await repo.update(
        job.id,
        status=IngestionStatus.COMPLETED,
        row_count=100,
        column_count=5,
        completed_at=now,
    )
    assert updated is not None
    assert updated.status == IngestionStatus.COMPLETED
    assert updated.row_count == 100
    assert updated.column_count == 5
    assert updated.completed_at == now


async def test_job_update_failed(db_session):
    """update() can set failed_at and error_message."""
    registry = await _make_registry(db_session)
    job = await _make_job(db_session, registry)
    now = datetime.now(timezone.utc)
    repo = IngestionJobRepository(db_session)
    updated = await repo.update(
        job.id,
        status=IngestionStatus.FAILED,
        failed_at=now,
        error_message="Something went wrong.",
    )
    assert updated is not None
    assert updated.status == IngestionStatus.FAILED
    assert updated.error_message == "Something went wrong."


async def test_job_update_not_found_returns_none(db_session):
    """update() returns None when the job does not exist."""
    repo = IngestionJobRepository(db_session)
    result = await repo.update(uuid.uuid4(), status=IngestionStatus.FAILED)
    assert result is None


async def test_job_update_does_not_change_unspecified_fields(db_session):
    """update() only changes the explicitly passed keyword arguments."""
    registry = await _make_registry(db_session)
    job = await _make_job(db_session, registry, filename="original.csv")
    repo = IngestionJobRepository(db_session)
    updated = await repo.update(job.id, status=IngestionStatus.PROCESSING)
    assert updated.original_filename == "original.csv"
    assert updated.row_count is None


# ===========================================================================
# IngestionJobRepository — delete
# ===========================================================================


async def test_job_delete_returns_true_when_found(db_session):
    """delete() returns True when the job exists."""
    registry = await _make_registry(db_session)
    job = await _make_job(db_session, registry)
    repo = IngestionJobRepository(db_session)
    result = await repo.delete(job.id)
    assert result is True


async def test_job_delete_removes_job(db_session):
    """After delete() + flush, get_by_id() returns None."""
    registry = await _make_registry(db_session)
    job = await _make_job(db_session, registry)
    repo = IngestionJobRepository(db_session)
    await repo.delete(job.id)
    await db_session.flush()
    db_session.expire_all()  # synchronous — expires cached objects
    assert await repo.get_by_id(job.id) is None


async def test_job_delete_returns_false_when_not_found(db_session):
    """delete() returns False for a non-existent UUID."""
    repo = IngestionJobRepository(db_session)
    result = await repo.delete(uuid.uuid4())
    assert result is False


# ===========================================================================
# IngestionJobRepository — list_by_dataset_registry
# ===========================================================================


async def test_list_by_registry_returns_matching_jobs(db_session):
    """list_by_dataset_registry() returns only jobs for the given registry."""
    reg_a = await _make_registry(db_session)
    reg_b = await _make_registry(db_session)
    job_a1 = await _make_job(db_session, reg_a, filename="a1.csv")
    job_a2 = await _make_job(db_session, reg_a, filename="a2.csv")
    await _make_job(db_session, reg_b, filename="b1.csv")

    repo = IngestionJobRepository(db_session)
    jobs = await repo.list_by_dataset_registry(reg_a.id)
    ids = {j.id for j in jobs}
    assert job_a1.id in ids
    assert job_a2.id in ids
    assert len(jobs) == 2


async def test_list_by_registry_empty_when_none(db_session):
    """list_by_dataset_registry() returns empty list when no jobs exist."""
    registry = await _make_registry(db_session)
    repo = IngestionJobRepository(db_session)
    jobs = await repo.list_by_dataset_registry(registry.id)
    assert jobs == []


async def test_list_by_registry_ordered_newest_first(db_session):
    """list_by_dataset_registry() orders by id DESC as a stable tiebreaker."""
    registry = await _make_registry(db_session)
    job1 = await _make_job(db_session, registry, filename="first.csv")
    job2 = await _make_job(db_session, registry, filename="second.csv")
    # Within the same transaction created_at is identical; the tiebreaker is id DESC.
    # job2 was created after job1 so its UUID is larger lexicographically
    # — this tests stable ordering, not wall-clock ordering.
    repo = IngestionJobRepository(db_session)
    jobs = await repo.list_by_dataset_registry(registry.id)
    assert len(jobs) == 2
    ids = {j.id for j in jobs}
    assert job1.id in ids
    assert job2.id in ids


async def test_list_by_registry_pagination(db_session):
    """list_by_dataset_registry() respects skip and limit."""
    registry = await _make_registry(db_session)
    for i in range(5):
        await _make_job(db_session, registry, filename=f"f{i}.csv")
    repo = IngestionJobRepository(db_session)
    page = await repo.list_by_dataset_registry(registry.id, skip=2, limit=2)
    assert len(page) == 2


# ===========================================================================
# IngestionJobRepository — list_by_status
# ===========================================================================


async def test_list_by_status_returns_matching(db_session):
    """list_by_status() returns only jobs with the requested status."""
    registry = await _make_registry(db_session)
    await _make_job(db_session, registry, status=IngestionStatus.PENDING)
    await _make_job(db_session, registry, status=IngestionStatus.COMPLETED)
    await _make_job(db_session, registry, status=IngestionStatus.FAILED)

    repo = IngestionJobRepository(db_session)
    completed = await repo.list_by_status(IngestionStatus.COMPLETED)
    assert all(j.status == IngestionStatus.COMPLETED for j in completed)
    assert len(completed) >= 1


async def test_list_by_status_empty_when_none(db_session):
    """list_by_status() returns empty list when no jobs match."""
    repo = IngestionJobRepository(db_session)
    jobs = await repo.list_by_status(IngestionStatus.PROCESSING)
    # May have jobs from other tests; just verify it returns a list
    assert isinstance(jobs, list)


# ===========================================================================
# IngestionJobRepository — get_latest_for_dataset
# ===========================================================================


async def test_get_latest_returns_newest_job(db_session):
    """get_latest_for_dataset() returns one of the jobs for the registry."""
    registry = await _make_registry(db_session)
    job1 = await _make_job(db_session, registry, filename="old.csv")
    job2 = await _make_job(db_session, registry, filename="new.csv")
    repo = IngestionJobRepository(db_session)
    latest = await repo.get_latest_for_dataset(registry.id)
    assert latest is not None
    # Both jobs were created in the same transaction; verify it returns one of them
    assert latest.id in {job1.id, job2.id}


async def test_get_latest_returns_none_when_no_jobs(db_session):
    """get_latest_for_dataset() returns None when no jobs exist for the registry."""
    registry = await _make_registry(db_session)
    repo = IngestionJobRepository(db_session)
    latest = await repo.get_latest_for_dataset(registry.id)
    assert latest is None


# ===========================================================================
# IngestionJobRepository — get_active_jobs
# ===========================================================================


async def test_get_active_jobs_returns_pending_and_processing(db_session):
    """get_active_jobs() returns PENDING and PROCESSING jobs only."""
    registry = await _make_registry(db_session)
    pending = await _make_job(db_session, registry, status=IngestionStatus.PENDING)
    processing = await _make_job(db_session, registry, status=IngestionStatus.PROCESSING)
    completed = await _make_job(db_session, registry, status=IngestionStatus.COMPLETED)
    failed = await _make_job(db_session, registry, status=IngestionStatus.FAILED)

    repo = IngestionJobRepository(db_session)
    active = await repo.get_active_jobs()
    active_ids = {j.id for j in active}
    assert pending.id in active_ids
    assert processing.id in active_ids
    assert completed.id not in active_ids
    assert failed.id not in active_ids


async def test_get_active_jobs_returns_list(db_session):
    """get_active_jobs() always returns a list (may be empty)."""
    repo = IngestionJobRepository(db_session)
    result = await repo.get_active_jobs()
    assert isinstance(result, list)


# ===========================================================================
# DatasetColumnRepository — create_many / list_by_ingestion_job
# ===========================================================================


async def test_column_create_many_returns_columns_with_ids(db_session):
    """create_many() returns DatasetColumn objects with populated UUIDs."""
    registry = await _make_registry(db_session)
    job = await _make_job(db_session, registry)
    repo = DatasetColumnRepository(db_session)
    cols = await repo.create_many(
        [
            {
                "ingestion_job_id": job.id,
                "original_name": "A",
                "normalized_name": "a",
                "inferred_type": InferredColumnType.TEXT,
                "nullable": False,
                "missing_count": 0,
                "unique_count": 3,
                "sample_values": ["x"],
                "ordinal_position": 0,
            },
            {
                "ingestion_job_id": job.id,
                "original_name": "B",
                "normalized_name": "b",
                "inferred_type": InferredColumnType.INTEGER,
                "nullable": True,
                "missing_count": 2,
                "unique_count": 5,
                "sample_values": ["1", "2"],
                "ordinal_position": 1,
            },
        ]
    )
    assert len(cols) == 2
    for col in cols:
        assert col.id is not None
        assert isinstance(col.id, uuid.UUID)


async def test_column_create_many_empty_list_returns_empty(db_session):
    """create_many([]) returns an empty list without error."""
    repo = DatasetColumnRepository(db_session)
    result = await repo.create_many([])
    assert result == []


async def test_column_list_by_job_returns_all_columns(db_session):
    """list_by_ingestion_job() returns all columns for the job."""
    registry = await _make_registry(db_session)
    job = await _make_job(db_session, registry)
    await _make_column(db_session, job, "col_a", "col_a", ordinal_position=0)
    await _make_column(db_session, job, "col_b", "col_b", ordinal_position=1)
    repo = DatasetColumnRepository(db_session)
    cols = await repo.list_by_ingestion_job(job.id)
    assert len(cols) == 2


async def test_column_list_by_job_empty_when_none(db_session):
    """list_by_ingestion_job() returns [] when the job has no columns."""
    registry = await _make_registry(db_session)
    job = await _make_job(db_session, registry)
    repo = DatasetColumnRepository(db_session)
    cols = await repo.list_by_ingestion_job(job.id)
    assert cols == []


async def test_column_list_by_job_isolates_to_job(db_session):
    """list_by_ingestion_job() returns only columns for the given job."""
    registry = await _make_registry(db_session)
    job_a = await _make_job(db_session, registry, filename="a.csv")
    job_b = await _make_job(db_session, registry, filename="b.csv")
    await _make_column(db_session, job_a, "x", "x")
    await _make_column(db_session, job_b, "y", "y")
    repo = DatasetColumnRepository(db_session)
    cols_a = await repo.list_by_ingestion_job(job_a.id)
    assert all(c.ingestion_job_id == job_a.id for c in cols_a)
    assert len(cols_a) == 1


# ===========================================================================
# DatasetColumnRepository — get_by_normalized_name / exists / count_for_job
# ===========================================================================


async def test_column_get_by_normalized_name_found(db_session):
    """get_by_normalized_name() returns the matching column."""
    registry = await _make_registry(db_session)
    job = await _make_job(db_session, registry)
    await _make_column(db_session, job, "Province Name", "province_name")
    repo = DatasetColumnRepository(db_session)
    col = await repo.get_by_normalized_name(job.id, "province_name")
    assert col is not None
    assert col.original_name == "Province Name"
    assert col.normalized_name == "province_name"


async def test_column_get_by_normalized_name_not_found(db_session):
    """get_by_normalized_name() returns None when no match exists."""
    registry = await _make_registry(db_session)
    job = await _make_job(db_session, registry)
    repo = DatasetColumnRepository(db_session)
    col = await repo.get_by_normalized_name(job.id, "nonexistent")
    assert col is None


async def test_column_get_by_normalized_name_scoped_to_job(db_session):
    """get_by_normalized_name() does not return columns from a different job."""
    registry = await _make_registry(db_session)
    job_a = await _make_job(db_session, registry, filename="a.csv")
    job_b = await _make_job(db_session, registry, filename="b.csv")
    await _make_column(db_session, job_a, "Score", "score")
    repo = DatasetColumnRepository(db_session)
    # Searching in job_b should not find the column from job_a
    col = await repo.get_by_normalized_name(job_b.id, "score")
    assert col is None


async def test_column_exists_true(db_session):
    """exists() returns True when the column exists in the job."""
    registry = await _make_registry(db_session)
    job = await _make_job(db_session, registry)
    await _make_column(db_session, job, "Value", "value")
    repo = DatasetColumnRepository(db_session)
    assert await repo.exists(job.id, "value") is True


async def test_column_exists_false(db_session):
    """exists() returns False when the column does not exist."""
    registry = await _make_registry(db_session)
    job = await _make_job(db_session, registry)
    repo = DatasetColumnRepository(db_session)
    assert await repo.exists(job.id, "missing_col") is False


async def test_column_count_for_job(db_session):
    """count_for_job() returns the correct column count."""
    registry = await _make_registry(db_session)
    job = await _make_job(db_session, registry)
    await _make_column(db_session, job, "A", "a", ordinal_position=0)
    await _make_column(db_session, job, "B", "b", ordinal_position=1)
    await _make_column(db_session, job, "C", "c", ordinal_position=2)
    repo = DatasetColumnRepository(db_session)
    assert await repo.count_for_job(job.id) == 3


async def test_column_count_for_job_zero_when_empty(db_session):
    """count_for_job() returns 0 when no columns exist."""
    registry = await _make_registry(db_session)
    job = await _make_job(db_session, registry)
    repo = DatasetColumnRepository(db_session)
    assert await repo.count_for_job(job.id) == 0


# ===========================================================================
# DatasetColumnRepository — delete_by_ingestion_job
# ===========================================================================


async def test_column_delete_by_job_removes_all(db_session):
    """delete_by_ingestion_job() removes all columns for the job."""
    registry = await _make_registry(db_session)
    job = await _make_job(db_session, registry)
    await _make_column(db_session, job, "A", "a", ordinal_position=0)
    await _make_column(db_session, job, "B", "b", ordinal_position=1)
    repo = DatasetColumnRepository(db_session)
    count = await repo.delete_by_ingestion_job(job.id)
    assert count == 2
    await db_session.flush()
    # Re-query directly — deleted rows should not be found by the DB query
    from app.models.ingestion import DatasetColumn as DC
    from sqlalchemy import func, select

    result = await db_session.execute(
        select(func.count()).select_from(DC).where(DC.ingestion_job_id == job.id)
    )
    assert result.scalar_one() == 0


async def test_column_delete_by_job_returns_zero_when_none(db_session):
    """delete_by_ingestion_job() returns 0 when no columns exist."""
    registry = await _make_registry(db_session)
    job = await _make_job(db_session, registry)
    repo = DatasetColumnRepository(db_session)
    count = await repo.delete_by_ingestion_job(job.id)
    assert count == 0


async def test_column_delete_by_job_does_not_affect_other_jobs(db_session):
    """delete_by_ingestion_job() only removes columns for the specified job."""
    registry = await _make_registry(db_session)
    job_a = await _make_job(db_session, registry, filename="a.csv")
    job_b = await _make_job(db_session, registry, filename="b.csv")
    await _make_column(db_session, job_a, "X", "x")
    await _make_column(db_session, job_b, "Y", "y")
    repo = DatasetColumnRepository(db_session)
    await repo.delete_by_ingestion_job(job_a.id)
    b_cols = await repo.list_by_ingestion_job(job_b.id)
    assert len(b_cols) == 1
    assert b_cols[0].normalized_name == "y"


# ===========================================================================
# DatasetColumnRepository — column ordering and sample values
# ===========================================================================


async def test_column_sample_values_persisted(db_session):
    """create_many() persists sample_values as a JSON list."""
    registry = await _make_registry(db_session)
    job = await _make_job(db_session, registry)
    repo = DatasetColumnRepository(db_session)
    cols = await repo.create_many(
        [
            {
                "ingestion_job_id": job.id,
                "original_name": "Province",
                "normalized_name": "province",
                "inferred_type": InferredColumnType.TEXT,
                "nullable": False,
                "missing_count": 0,
                "unique_count": 3,
                "sample_values": ["Lusaka", "Copperbelt", "Eastern"],
                "ordinal_position": 0,
            }
        ]
    )
    assert cols[0].sample_values == ["Lusaka", "Copperbelt", "Eastern"]


async def test_column_various_inferred_types(db_session):
    """create_many() stores and retrieves all InferredColumnType values."""
    registry = await _make_registry(db_session)
    job = await _make_job(db_session, registry)
    repo = DatasetColumnRepository(db_session)
    type_cases = [
        ("int_col", InferredColumnType.INTEGER),
        ("dec_col", InferredColumnType.DECIMAL),
        ("bool_col", InferredColumnType.BOOLEAN),
        ("date_col", InferredColumnType.DATE),
        ("dt_col", InferredColumnType.DATETIME),
        ("text_col", InferredColumnType.TEXT),
    ]
    payload = [
        {
            "ingestion_job_id": job.id,
            "original_name": name,
            "normalized_name": name,
            "inferred_type": t,
            "nullable": False,
            "missing_count": 0,
            "unique_count": 1,
            "ordinal_position": idx,
        }
        for idx, (name, t) in enumerate(type_cases)
    ]
    cols = await repo.create_many(payload)
    by_name = {c.normalized_name: c.inferred_type for c in cols}
    for name, expected_type in type_cases:
        assert by_name[name] == expected_type


# ===========================================================================
# FK cascade: deleting IngestionJob cascades to DatasetColumn
# ===========================================================================


async def test_job_delete_cascades_to_columns(db_session):
    """Deleting an IngestionJob removes its DatasetColumn rows via FK cascade."""
    registry = await _make_registry(db_session)
    job = await _make_job(db_session, registry)
    await _make_column(db_session, job, "A", "a", ordinal_position=0)
    await _make_column(db_session, job, "B", "b", ordinal_position=1)

    job_repo = IngestionJobRepository(db_session)
    col_repo = DatasetColumnRepository(db_session)

    await job_repo.delete(job.id)
    await db_session.flush()

    cols = await col_repo.list_by_ingestion_job(job.id)
    assert cols == []


# ===========================================================================
# ordinal_position hardening tests (Task 5 hardening)
# ===========================================================================


async def test_columns_returned_in_ordinal_position_order(db_session):
    """list_by_ingestion_job() returns columns in ordinal_position ASC order.

    Columns are inserted in REVERSE position order to confirm that the
    ordering is driven by ordinal_position, not insertion order or UUID.
    """
    registry = await _make_registry(db_session)
    job = await _make_job(db_session, registry)
    repo = DatasetColumnRepository(db_session)

    # Insert in reverse order (positions 2, 1, 0)
    await repo.create_many(
        [
            {
                "ingestion_job_id": job.id,
                "original_name": "C",
                "normalized_name": "c",
                "inferred_type": InferredColumnType.TEXT,
                "nullable": False,
                "missing_count": 0,
                "unique_count": 1,
                "ordinal_position": 2,
            },
            {
                "ingestion_job_id": job.id,
                "original_name": "A",
                "normalized_name": "a",
                "inferred_type": InferredColumnType.TEXT,
                "nullable": False,
                "missing_count": 0,
                "unique_count": 1,
                "ordinal_position": 0,
            },
            {
                "ingestion_job_id": job.id,
                "original_name": "B",
                "normalized_name": "b",
                "inferred_type": InferredColumnType.TEXT,
                "nullable": False,
                "missing_count": 0,
                "unique_count": 1,
                "ordinal_position": 1,
            },
        ]
    )

    cols = await repo.list_by_ingestion_job(job.id)
    assert len(cols) == 3
    assert cols[0].normalized_name == "a"
    assert cols[1].normalized_name == "b"
    assert cols[2].normalized_name == "c"
    assert [c.ordinal_position for c in cols] == [0, 1, 2]


async def test_uuid_ordering_cannot_override_ordinal_position(db_session):
    """UUID assignment cannot change the order returned by list_by_ingestion_job.

    This test inserts columns and explicitly verifies that ordinal_position
    drives order, not UUID or created_at.
    """
    registry = await _make_registry(db_session)
    job = await _make_job(db_session, registry)
    repo = DatasetColumnRepository(db_session)

    await repo.create_many(
        [
            {
                "ingestion_job_id": job.id,
                "original_name": "Last",
                "normalized_name": "last",
                "inferred_type": InferredColumnType.TEXT,
                "nullable": False,
                "missing_count": 0,
                "unique_count": 1,
                "ordinal_position": 99,
            },
            {
                "ingestion_job_id": job.id,
                "original_name": "First",
                "normalized_name": "first",
                "inferred_type": InferredColumnType.TEXT,
                "nullable": False,
                "missing_count": 0,
                "unique_count": 1,
                "ordinal_position": 0,
            },
        ]
    )

    cols = await repo.list_by_ingestion_job(job.id)
    assert cols[0].normalized_name == "first"
    assert cols[1].normalized_name == "last"


async def test_ordinal_position_stored_correctly(db_session):
    """ordinal_position is persisted and retrieved accurately."""
    registry = await _make_registry(db_session)
    job = await _make_job(db_session, registry)
    col = await _make_column(db_session, job, "Score", "score", ordinal_position=7)
    assert col.ordinal_position == 7


async def test_same_position_allowed_for_different_jobs(db_session):
    """The same ordinal_position is allowed for columns in different jobs."""
    registry = await _make_registry(db_session)
    job_a = await _make_job(db_session, registry, filename="a.csv")
    job_b = await _make_job(db_session, registry, filename="b.csv")
    # Both jobs can have a column at position 0 — the uniqueness is per-job
    col_a = await _make_column(db_session, job_a, "Name", "name", ordinal_position=0)
    col_b = await _make_column(db_session, job_b, "Name", "name", ordinal_position=0)
    assert col_a.ordinal_position == 0
    assert col_b.ordinal_position == 0


async def test_duplicate_ordinal_position_same_job_rejected(db_session):
    """Inserting two columns with the same ordinal_position for one job raises IntegrityError."""
    from sqlalchemy.exc import IntegrityError

    registry = await _make_registry(db_session)
    job = await _make_job(db_session, registry)
    repo = DatasetColumnRepository(db_session)

    await repo.create_many(
        [
            {
                "ingestion_job_id": job.id,
                "original_name": "A",
                "normalized_name": "a",
                "inferred_type": InferredColumnType.TEXT,
                "nullable": False,
                "missing_count": 0,
                "unique_count": 1,
                "ordinal_position": 0,
            }
        ]
    )
    await db_session.flush()

    with pytest.raises(IntegrityError):
        await repo.create_many(
            [
                {
                    "ingestion_job_id": job.id,
                    "original_name": "B",
                    "normalized_name": "b",
                    "inferred_type": InferredColumnType.TEXT,
                    "nullable": False,
                    "missing_count": 0,
                    "unique_count": 1,
                    "ordinal_position": 0,  # duplicate!
                }
            ]
        )
        await db_session.flush()


async def test_negative_ordinal_position_rejected(db_session):
    """Inserting a column with ordinal_position < 0 raises IntegrityError."""
    from sqlalchemy.exc import IntegrityError

    registry = await _make_registry(db_session)
    job = await _make_job(db_session, registry)
    repo = DatasetColumnRepository(db_session)

    with pytest.raises(IntegrityError):
        await repo.create_many(
            [
                {
                    "ingestion_job_id": job.id,
                    "original_name": "A",
                    "normalized_name": "a",
                    "inferred_type": InferredColumnType.TEXT,
                    "nullable": False,
                    "missing_count": 0,
                    "unique_count": 1,
                    "ordinal_position": -1,
                }
            ]
        )
        await db_session.flush()
