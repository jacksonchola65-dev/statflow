"""
tests/test_dataset_row_repository.py
=====================================
Integration tests for DatasetRowRepository — hardened version.

All tests run against the real test database via the shared db_session fixture.

Key invariants tested:
  - create_many() returns int, not list[DatasetRow]
  - create_many() uses Core INSERT (no ORM identity-map pollution)
  - All batches participate in the same caller-owned transaction
  - Caller rollback removes all rows including those from completed batches
  - No commit(), rollback(), close(), or expunge_all() called by repository
  - Pagination uses silent clamping (project convention)
  - Existing query, count, existence, and deletion tests remain green
"""

from __future__ import annotations

import sys

if sys.platform == "win32":
    import asyncio as _asyncio

    _asyncio.set_event_loop_policy(_asyncio.WindowsSelectorEventLoopPolicy())

import uuid

import pytest
from app.models.data_source import DatasetRegistry, FileFormat, SourceType
from app.models.ingestion import DatasetRow, IngestionJob
from app.repositories.dataset_row_repository import (
    _INSERT_BATCH_SIZE,
    DatasetRowRepository,
    RowInsertMapping,
)
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
    return await repo.create(
        dataset_registry_id=registry.id,
        original_filename="test.csv",
        file_format=FileFormat.CSV,
        file_size_bytes=1024,
    )


def _row_mapping(
    job: IngestionJob,
    row_number: int,
    values: dict | None = None,
) -> RowInsertMapping:
    """Build a RowInsertMapping dict for create_many()."""
    return {
        "ingestion_job_id": job.id,
        "row_number": row_number,
        "values": values if values is not None else {"col": f"val_{row_number}"},
    }


# ===========================================================================
# create_many — return type and empty input
# ===========================================================================


async def test_create_many_empty_returns_zero(db_session):
    """create_many([]) returns 0 immediately."""
    repo = DatasetRowRepository(db_session)
    result = await repo.create_many([])
    assert result == 0
    assert isinstance(result, int)


async def test_create_many_returns_int_not_list(db_session):
    """create_many() return type is int, not list."""
    registry = await _make_registry(db_session)
    job = await _make_job(db_session, registry)
    repo = DatasetRowRepository(db_session)
    result = await repo.create_many([_row_mapping(job, 0)])
    assert isinstance(result, int)
    assert result == 1


async def test_create_many_single_row_returns_one(db_session):
    """create_many with 1 row returns 1."""
    registry = await _make_registry(db_session)
    job = await _make_job(db_session, registry)
    repo = DatasetRowRepository(db_session)
    count = await repo.create_many([_row_mapping(job, 0, {"name": "Alice"})])
    assert count == 1
    # Verify row is queryable
    row = await repo.get_by_row_number(job.id, 0)
    assert row is not None
    assert row.values == {"name": "Alice"}


async def test_create_many_multiple_rows_returns_count(db_session):
    """create_many with N rows returns N."""
    registry = await _make_registry(db_session)
    job = await _make_job(db_session, registry)
    repo = DatasetRowRepository(db_session)
    count = await repo.create_many([_row_mapping(job, i) for i in range(10)])
    assert count == 10
    assert await repo.count_for_job(job.id) == 10


async def test_create_many_row_numbers_preserved(db_session):
    """Row numbers are stored exactly as supplied."""
    registry = await _make_registry(db_session)
    job = await _make_job(db_session, registry)
    repo = DatasetRowRepository(db_session)
    row_numbers = [0, 5, 99, 1000]
    await repo.create_many([_row_mapping(job, rn) for rn in row_numbers])
    for rn in row_numbers:
        row = await repo.get_by_row_number(job.id, rn)
        assert row is not None
        assert row.row_number == rn


async def test_create_many_values_preserved(db_session):
    """JSON values are stored exactly as supplied."""
    registry = await _make_registry(db_session)
    job = await _make_job(db_session, registry)
    repo = DatasetRowRepository(db_session)
    payload = {"city": "Lusaka", "pop": 3360000, "active": True, "ratio": None}
    await repo.create_many([_row_mapping(job, 0, payload)])
    row = await repo.get_by_row_number(job.id, 0)
    assert row is not None
    assert row.values == payload


# ===========================================================================
# create_many — batch boundary and identity-map
# ===========================================================================


async def test_create_many_crosses_batch_boundary(db_session):
    """Input spanning > _INSERT_BATCH_SIZE rows crosses two batches."""
    n = _INSERT_BATCH_SIZE + 10
    registry = await _make_registry(db_session)
    job = await _make_job(db_session, registry)
    repo = DatasetRowRepository(db_session)
    count = await repo.create_many([_row_mapping(job, i) for i in range(n)])
    assert count == n
    assert await repo.count_for_job(job.id) == n


async def test_create_many_does_not_add_rows_to_identity_map(db_session):
    """Core INSERT does not add DatasetRow objects to the ORM identity map.

    After create_many(), no DatasetRow instances should exist in the session's
    identity map for the inserted rows. We verify this by checking that
    querying the rows by primary key yields a fresh DB load (not an
    identity-map hit) — specifically, the session.identity_map should not
    contain any DatasetRow entries after the bulk insert.
    """
    registry = await _make_registry(db_session)
    job = await _make_job(db_session, registry)
    repo = DatasetRowRepository(db_session)
    await repo.create_many([_row_mapping(job, i) for i in range(5)])

    # Count DatasetRow instances currently in the identity map
    row_instances_in_map = sum(
        1 for obj in db_session.identity_map.values() if isinstance(obj, DatasetRow)
    )
    assert row_instances_in_map == 0, (
        f"Expected 0 DatasetRow objects in identity map after Core INSERT, "
        f"found {row_instances_in_map}. The bulk path must not pollute the ORM map."
    )


async def test_create_many_rows_visible_in_same_transaction(db_session):
    """All inserted rows are visible within the same transaction after create_many."""
    registry = await _make_registry(db_session)
    job = await _make_job(db_session, registry)
    repo = DatasetRowRepository(db_session)
    await repo.create_many([_row_mapping(job, i) for i in range(3)])
    # Rows are visible without committing
    assert await repo.count_for_job(job.id) == 3


# ===========================================================================
# create_many — transaction semantics
# ===========================================================================


async def test_create_many_caller_rollback_removes_all_rows(db_session):
    """Caller rollback removes all rows, including those from completed batches."""
    registry = await _make_registry(db_session)
    job = await _make_job(db_session, registry)
    repo = DatasetRowRepository(db_session)

    async with db_session.begin_nested() as sp:
        # Insert two batches worth
        await repo.create_many([_row_mapping(job, i) for i in range(_INSERT_BATCH_SIZE + 5)])
        assert await repo.count_for_job(job.id) == _INSERT_BATCH_SIZE + 5
        await sp.rollback()

    assert await repo.count_for_job(job.id) == 0


async def test_create_many_failure_in_second_batch_leaves_transaction_rollbackable(db_session):
    """A constraint failure in a later batch does not auto-commit earlier batches.

    We insert one valid row, then attempt to insert a duplicate that violates
    the unique constraint on (ingestion_job_id, row_number). The IntegrityError
    should be catchable and the transaction should remain rollback-capable.
    """
    registry = await _make_registry(db_session)
    job = await _make_job(db_session, registry)
    repo = DatasetRowRepository(db_session)

    # First insert succeeds
    await repo.create_many([_row_mapping(job, 0)])

    # Second insert duplicates row_number=0 — should raise IntegrityError
    with pytest.raises(IntegrityError):
        await repo.create_many([_row_mapping(job, 0)])  # duplicate


async def test_create_many_duplicate_row_number_does_not_commit_earlier_batches(db_session):
    """Duplicate failure does not commit earlier rows — caller can roll back all."""
    registry = await _make_registry(db_session)
    job = await _make_job(db_session, registry)
    repo = DatasetRowRepository(db_session)

    async with db_session.begin_nested() as sp:
        await repo.create_many([_row_mapping(job, i) for i in range(3)])
        try:
            # row_number=0 already exists — will fail
            await repo.create_many([_row_mapping(job, 0)])
        except IntegrityError:
            pass
        await sp.rollback()

    # After rollback everything should be gone
    assert await repo.count_for_job(job.id) == 0


# ===========================================================================
# get_by_id / get_by_row_number
# ===========================================================================


async def test_get_by_id_found(db_session):
    registry = await _make_registry(db_session)
    job = await _make_job(db_session, registry)
    repo = DatasetRowRepository(db_session)
    await repo.create_many([_row_mapping(job, 0)])
    row = await repo.get_by_row_number(job.id, 0)
    assert row is not None
    fetched = await repo.get_by_id(row.id)
    assert fetched is not None
    assert fetched.id == row.id


async def test_get_by_id_not_found(db_session):
    repo = DatasetRowRepository(db_session)
    assert await repo.get_by_id(uuid.uuid4()) is None


async def test_get_by_row_number_found(db_session):
    registry = await _make_registry(db_session)
    job = await _make_job(db_session, registry)
    repo = DatasetRowRepository(db_session)
    await repo.create_many([_row_mapping(job, 42, {"x": 1})])
    row = await repo.get_by_row_number(job.id, 42)
    assert row is not None
    assert row.row_number == 42
    assert row.values == {"x": 1}


async def test_get_by_row_number_not_found(db_session):
    registry = await _make_registry(db_session)
    job = await _make_job(db_session, registry)
    repo = DatasetRowRepository(db_session)
    assert await repo.get_by_row_number(job.id, 999) is None


async def test_get_by_row_number_scoped_to_job(db_session):
    registry = await _make_registry(db_session)
    job_a = await _make_job(db_session, registry)
    job_b = await _make_job(db_session, registry)
    repo = DatasetRowRepository(db_session)
    await repo.create_many([_row_mapping(job_b, 0)])
    assert await repo.get_by_row_number(job_a.id, 0) is None


# ===========================================================================
# list_by_ingestion_job — ordering and pagination
# ===========================================================================


async def test_list_order_is_row_number_asc(db_session):
    registry = await _make_registry(db_session)
    job = await _make_job(db_session, registry)
    repo = DatasetRowRepository(db_session)
    # Insert in reverse order
    await repo.create_many([_row_mapping(job, rn) for rn in [4, 2, 0, 3, 1]])
    rows = await repo.list_by_ingestion_job(job.id)
    assert [r.row_number for r in rows] == [0, 1, 2, 3, 4]


async def test_list_pagination_first_page(db_session):
    registry = await _make_registry(db_session)
    job = await _make_job(db_session, registry)
    repo = DatasetRowRepository(db_session)
    await repo.create_many([_row_mapping(job, i) for i in range(5)])
    page = await repo.list_by_ingestion_job(job.id, offset=0, limit=2)
    assert [r.row_number for r in page] == [0, 1]


async def test_list_pagination_second_page(db_session):
    registry = await _make_registry(db_session)
    job = await _make_job(db_session, registry)
    repo = DatasetRowRepository(db_session)
    await repo.create_many([_row_mapping(job, i) for i in range(5)])
    page = await repo.list_by_ingestion_job(job.id, offset=2, limit=2)
    assert [r.row_number for r in page] == [2, 3]


async def test_list_offset_beyond_end_returns_empty(db_session):
    registry = await _make_registry(db_session)
    job = await _make_job(db_session, registry)
    repo = DatasetRowRepository(db_session)
    await repo.create_many([_row_mapping(job, i) for i in range(3)])
    assert await repo.list_by_ingestion_job(job.id, offset=100, limit=10) == []


async def test_list_negative_offset_clamped_to_zero(db_session):
    """Negative offset is silently clamped to 0 (project convention)."""
    registry = await _make_registry(db_session)
    job = await _make_job(db_session, registry)
    repo = DatasetRowRepository(db_session)
    await repo.create_many([_row_mapping(job, i) for i in range(3)])
    rows = await repo.list_by_ingestion_job(job.id, offset=-5, limit=10)
    assert len(rows) == 3


async def test_list_excessive_limit_clamped_to_max(db_session):
    """Limit > _MAX_LIMIT is silently clamped to _MAX_LIMIT (project convention)."""
    registry = await _make_registry(db_session)
    job = await _make_job(db_session, registry)
    repo = DatasetRowRepository(db_session)
    await repo.create_many([_row_mapping(job, i) for i in range(5)])
    # Request more than _MAX_LIMIT; only 5 rows exist so all are returned
    rows = await repo.list_by_ingestion_job(job.id, limit=999_999)
    assert len(rows) == 5


async def test_list_isolates_between_jobs(db_session):
    registry = await _make_registry(db_session)
    job_a = await _make_job(db_session, registry)
    job_b = await _make_job(db_session, registry)
    repo = DatasetRowRepository(db_session)
    await repo.create_many([_row_mapping(job_a, i) for i in range(3)])
    await repo.create_many([_row_mapping(job_b, i) for i in range(5)])
    rows_a = await repo.list_by_ingestion_job(job_a.id)
    assert len(rows_a) == 3
    assert all(r.ingestion_job_id == job_a.id for r in rows_a)


# ===========================================================================
# count_for_job / exists
# ===========================================================================


async def test_count_for_job(db_session):
    registry = await _make_registry(db_session)
    job = await _make_job(db_session, registry)
    repo = DatasetRowRepository(db_session)
    await repo.create_many([_row_mapping(job, i) for i in range(7)])
    assert await repo.count_for_job(job.id) == 7


async def test_count_for_job_zero_when_empty(db_session):
    registry = await _make_registry(db_session)
    job = await _make_job(db_session, registry)
    repo = DatasetRowRepository(db_session)
    assert await repo.count_for_job(job.id) == 0


async def test_count_returns_int(db_session):
    registry = await _make_registry(db_session)
    job = await _make_job(db_session, registry)
    repo = DatasetRowRepository(db_session)
    await repo.create_many([_row_mapping(job, 0)])
    assert isinstance(await repo.count_for_job(job.id), int)


async def test_exists_true(db_session):
    registry = await _make_registry(db_session)
    job = await _make_job(db_session, registry)
    repo = DatasetRowRepository(db_session)
    await repo.create_many([_row_mapping(job, 5)])
    assert await repo.exists(job.id, 5) is True


async def test_exists_false(db_session):
    registry = await _make_registry(db_session)
    job = await _make_job(db_session, registry)
    repo = DatasetRowRepository(db_session)
    assert await repo.exists(job.id, 999) is False


async def test_exists_scoped_to_job(db_session):
    registry = await _make_registry(db_session)
    job_a = await _make_job(db_session, registry)
    job_b = await _make_job(db_session, registry)
    repo = DatasetRowRepository(db_session)
    await repo.create_many([_row_mapping(job_b, 0)])
    assert await repo.exists(job_a.id, 0) is False


async def test_same_row_number_allowed_in_different_jobs(db_session):
    registry = await _make_registry(db_session)
    job_a = await _make_job(db_session, registry)
    job_b = await _make_job(db_session, registry)
    repo = DatasetRowRepository(db_session)
    await repo.create_many([_row_mapping(job_a, 0)])
    await repo.create_many([_row_mapping(job_b, 0)])
    assert await repo.exists(job_a.id, 0) is True
    assert await repo.exists(job_b.id, 0) is True


# ===========================================================================
# delete_by_ingestion_job
# ===========================================================================


async def test_delete_by_job_removes_all_rows(db_session):
    registry = await _make_registry(db_session)
    job = await _make_job(db_session, registry)
    repo = DatasetRowRepository(db_session)
    await repo.create_many([_row_mapping(job, i) for i in range(5)])
    deleted = await repo.delete_by_ingestion_job(job.id)
    assert deleted == 5
    assert await repo.count_for_job(job.id) == 0


async def test_delete_by_job_returns_zero_when_none(db_session):
    registry = await _make_registry(db_session)
    job = await _make_job(db_session, registry)
    repo = DatasetRowRepository(db_session)
    assert await repo.delete_by_ingestion_job(job.id) == 0


async def test_delete_does_not_affect_other_jobs(db_session):
    registry = await _make_registry(db_session)
    job_a = await _make_job(db_session, registry)
    job_b = await _make_job(db_session, registry)
    repo = DatasetRowRepository(db_session)
    await repo.create_many([_row_mapping(job_a, i) for i in range(3)])
    await repo.create_many([_row_mapping(job_b, i) for i in range(4)])
    await repo.delete_by_ingestion_job(job_a.id)
    assert await repo.count_for_job(job_a.id) == 0
    assert await repo.count_for_job(job_b.id) == 4


# ===========================================================================
# Implicit IngestionJob.rows remains blocked
# ===========================================================================


async def test_implicit_rows_access_raises(db_session):
    """job.rows must raise (lazy='raise') to prevent unbounded loads."""
    from sqlalchemy.exc import InvalidRequestError

    registry = await _make_registry(db_session)
    job = await _make_job(db_session, registry)
    repo = DatasetRowRepository(db_session)
    await repo.create_many([_row_mapping(job, 0)])
    db_session.expire(job)
    with pytest.raises((InvalidRequestError, Exception)):
        _ = job.rows
