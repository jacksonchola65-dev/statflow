"""
tests/test_ingestion_inspection_service.py
========================================

Unit and integration tests for the ingestion inspection service.

The service reads persisted ingestion job metadata, column profiles, and rows,
assembling a complete `DatasetInspectionResponse`.
"""

from __future__ import annotations

import sys
import uuid
from datetime import datetime, timezone

import pytest

from app.models.data_source import DatasetRegistry, FileFormat, SourceType
from app.models.ingestion import DatasetColumn, DatasetRow, IngestionJob, IngestionStatus, InferredColumnType
from app.repositories.dataset_column_repository import DatasetColumnRepository
from app.repositories.dataset_row_repository import DatasetRowRepository
from app.repositories.ingestion_job_repository import IngestionJobRepository
from app.services.ingestion_inspection_service import (
    IngestionInspectionService,
    IngestionJobNotFoundError,
    InvalidInspectionPaginationError,
)


if sys.platform == "win32":
    import asyncio as _asyncio
    _asyncio.set_event_loop_policy(_asyncio.WindowsSelectorEventLoopPolicy())


async def _make_registry(db_session) -> DatasetRegistry:
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


async def _make_job(db_session, registry: DatasetRegistry, status: IngestionStatus = IngestionStatus.COMPLETED) -> IngestionJob:
    repo = IngestionJobRepository(db_session)
    job = await repo.create(
        dataset_registry_id=registry.id,
        original_filename="test.csv",
        file_format=FileFormat.CSV,
        file_size_bytes=123,
        status=status,
    )
    return job


async def _make_column(db_session, job: IngestionJob, ordinal_position: int = 0) -> DatasetColumn:
    repo = DatasetColumnRepository(db_session)
    cols = await repo.create_many([
        {
            "ingestion_job_id": job.id,
            "original_name": f"Column {ordinal_position}",
            "normalized_name": f"column_{ordinal_position}",
            "inferred_type": InferredColumnType.TEXT,
            "nullable": False,
            "missing_count": 0,
            "unique_count": 2,
            "sample_values": ["a", "b"],
            "ordinal_position": ordinal_position,
        }
    ])
    return cols[0]


async def _make_row(db_session, job: IngestionJob, row_number: int = 0) -> DatasetRow:
    repo = DatasetRowRepository(db_session)
    await repo.create_many([
        {
            "ingestion_job_id": job.id,
            "row_number": row_number,
            "values": {"column_0": "a", "column_1": "b"},
        }
    ])
    result = await repo.get_by_row_number(job.id, row_number)
    assert result is not None
    return result


async def test_get_inspection_returns_complete_response(db_session):
    registry = await _make_registry(db_session)
    job = await _make_job(db_session, registry)
    await _make_column(db_session, job, ordinal_position=0)
    await _make_column(db_session, job, ordinal_position=1)
    await _make_row(db_session, job, row_number=0)
    await _make_row(db_session, job, row_number=1)

    service = IngestionInspectionService(db_session)
    response = await service.get_inspection(job.id, page=1, page_size=1)

    assert response.job.id == job.id
    assert len(response.columns) == 2
    assert len(response.rows) == 1
    assert response.pagination.page == 1
    assert response.pagination.page_size == 1
    assert response.pagination.total_items == 2
    assert response.pagination.total_pages == 2
    assert response.pagination.has_next is True
    assert response.pagination.has_previous is False


async def test_get_inspection_row_pagination(db_session):
    registry = await _make_registry(db_session)
    job = await _make_job(db_session, registry)
    await _make_column(db_session, job, ordinal_position=0)
    await _make_column(db_session, job, ordinal_position=1)
    await _make_row(db_session, job, row_number=0)
    await _make_row(db_session, job, row_number=1)
    await _make_row(db_session, job, row_number=2)

    service = IngestionInspectionService(db_session)
    response = await service.get_inspection(job.id, page=2, page_size=2)

    assert response.pagination.page == 2
    assert response.pagination.page_size == 2
    assert response.pagination.total_items == 3
    assert response.pagination.total_pages == 2
    assert response.pagination.has_next is False
    assert response.pagination.has_previous is True
    assert len(response.rows) == 1
    assert response.rows[0].row_number == 2


async def test_get_inspection_handles_missing_job(db_session):
    service = IngestionInspectionService(db_session)
    with pytest.raises(IngestionJobNotFoundError):
        await service.get_inspection(uuid.uuid4())


async def test_get_inspection_rejects_page_zero(db_session):
    registry = await _make_registry(db_session)
    job = await _make_job(db_session, registry)
    service = IngestionInspectionService(db_session)

    with pytest.raises(InvalidInspectionPaginationError):
        await service.get_inspection(job.id, page=0)


async def test_get_inspection_rejects_negative_page(db_session):
    registry = await _make_registry(db_session)
    job = await _make_job(db_session, registry)
    service = IngestionInspectionService(db_session)

    with pytest.raises(InvalidInspectionPaginationError):
        await service.get_inspection(job.id, page=-1)


async def test_get_inspection_rejects_page_size_zero(db_session):
    registry = await _make_registry(db_session)
    job = await _make_job(db_session, registry)
    service = IngestionInspectionService(db_session)

    with pytest.raises(InvalidInspectionPaginationError):
        await service.get_inspection(job.id, page_size=0)


async def test_get_inspection_rejects_negative_page_size(db_session):
    registry = await _make_registry(db_session)
    job = await _make_job(db_session, registry)
    service = IngestionInspectionService(db_session)

    with pytest.raises(InvalidInspectionPaginationError):
        await service.get_inspection(job.id, page_size=-10)


async def test_get_inspection_rejects_page_size_above_max(db_session):
    registry = await _make_registry(db_session)
    job = await _make_job(db_session, registry)
    service = IngestionInspectionService(db_session)

    with pytest.raises(InvalidInspectionPaginationError):
        await service.get_inspection(job.id, page_size=10_001)


async def test_get_inspection_accepts_maximum_page_size(db_session):
    registry = await _make_registry(db_session)
    job = await _make_job(db_session, registry)
    await _make_column(db_session, job, ordinal_position=0)
    await _make_row(db_session, job, row_number=0)

    service = IngestionInspectionService(db_session)
    response = await service.get_inspection(job.id, page=1, page_size=10_000)

    assert response.pagination.page_size == 10_000
    assert response.rows[0].values["column_0"] == "a"


async def test_get_inspection_page_beyond_total_returns_empty_rows(db_session):
    registry = await _make_registry(db_session)
    job = await _make_job(db_session, registry)
    await _make_column(db_session, job, ordinal_position=0)
    await _make_row(db_session, job, row_number=0)

    service = IngestionInspectionService(db_session)
    response = await service.get_inspection(job.id, page=2, page_size=10)

    assert response.pagination.page == 2
    assert response.pagination.total_pages == 1
    assert response.pagination.has_next is False
    assert response.pagination.has_previous is True
    assert response.rows == []


async def test_get_inspection_returns_empty_when_no_items(db_session):
    registry = await _make_registry(db_session)
    job = await _make_job(db_session, registry)

    service = IngestionInspectionService(db_session)
    response = await service.get_inspection(job.id, page=1, page_size=10)

    assert response.pagination.total_items == 0
    assert response.pagination.total_pages == 0
    assert response.pagination.has_next is False
    assert response.pagination.has_previous is False
    assert response.rows == []


async def test_get_inspection_preserves_decimal_strings(db_session):
    registry = await _make_registry(db_session)
    job = await _make_job(db_session, registry)
    await _make_column(db_session, job, ordinal_position=0)
    await _make_row(db_session, job, row_number=0)
    await _make_row(db_session, job, row_number=1)

    # Override the second row values to include a decimal string explicitly.
    row_repo = DatasetRowRepository(db_session)
    row = await row_repo.get_by_row_number(job.id, 1)
    row.values = {"column_0": "1.23"}
    await db_session.flush()

    service = IngestionInspectionService(db_session)
    response = await service.get_inspection(job.id, page=1, page_size=10)

    assert response.rows[1].values["column_0"] == "1.23"


async def test_get_inspection_repository_call_order(db_session, monkeypatch):
    registry = await _make_registry(db_session)
    job = await _make_job(db_session, registry)
    await _make_column(db_session, job, ordinal_position=0)

    call_order: list[str] = []

    class StubJobRepo:
        def __init__(self, session):
            pass

        async def get_by_id(self, ingestion_job_id):
            call_order.append("job")
            return job

    class StubColumnRepo:
        def __init__(self, session):
            pass

        async def list_by_ingestion_job(self, ingestion_job_id):
            call_order.append("columns")
            return []

    class StubRowRepo:
        def __init__(self, session):
            pass

        async def count_for_job(self, ingestion_job_id):
            call_order.append("count")
            return 1

        async def list_by_ingestion_job(self, ingestion_job_id, offset, limit):
            call_order.append("rows")
            assert offset == 10
            assert limit == 10
            return []

    import app.services.ingestion_inspection_service as svc_module

    monkeypatch.setattr(svc_module, "IngestionJobRepository", StubJobRepo)
    monkeypatch.setattr(svc_module, "DatasetColumnRepository", StubColumnRepo)
    monkeypatch.setattr(svc_module, "DatasetRowRepository", StubRowRepo)

    service = svc_module.IngestionInspectionService(db_session)
    await service.get_inspection(job.id, page=2, page_size=10)

    assert call_order == ["job", "columns", "count", "rows"]
