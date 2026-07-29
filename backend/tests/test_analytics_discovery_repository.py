from __future__ import annotations

import inspect
import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.analytics.discovery import DatasetDiscoveryRepository
from app.models.data_source import FileFormat, SourceType
from app.models.ingestion import IngestionStatus, InferredColumnType
from app.repositories.data_source_repository import DataSourceRepository
from app.repositories.dataset_column_repository import DatasetColumnRepository
from app.repositories.dataset_registry_repository import DatasetRegistryRepository
from app.repositories.dataset_row_repository import DatasetRowRepository
from app.repositories.ingestion_job_repository import IngestionJobRepository


async def _create_job(
    db_session: AsyncSession,
    *,
    status: IngestionStatus,
    completed_at: datetime | None = None,
    row_count: int = 0,
    columns: list[dict] | None = None,
    rows: list[dict] | None = None,
) -> uuid.UUID:
    source = await DataSourceRepository(db_session).create(name=f"Repo Source {uuid.uuid4().hex[:8]}", is_active=True)
    await db_session.flush()

    registry = await DatasetRegistryRepository(db_session).create(
        data_source_id=source.id,
        dataset_name=f"Repo Dataset {uuid.uuid4().hex[:8]}",
        source_type=SourceType.OFFICIAL,
        file_format=FileFormat.CSV,
    )
    await db_session.flush()

    job = await IngestionJobRepository(db_session).create(
        dataset_registry_id=registry.id,
        original_filename="repo.csv",
        file_format=FileFormat.CSV,
        file_size_bytes=100,
        status=status,
    )
    await db_session.flush()

    if columns is None:
        columns = [
            {
                "ordinal_position": 0,
                "original_name": "Name",
                "normalized_name": "name",
                "inferred_type": InferredColumnType.TEXT,
                "nullable": False,
                "missing_count": 0,
                "unique_count": 1,
                "sample_values": ["foo"],
            }
        ]

    for col in columns:
        col["ingestion_job_id"] = job.id
    await DatasetColumnRepository(db_session).create_many(columns)

    if rows is not None:
        for row in rows:
            row["ingestion_job_id"] = job.id
        await DatasetRowRepository(db_session).create_many(rows)

    await IngestionJobRepository(db_session).update(
        job.id,
        status=status,
        row_count=row_count,
        column_count=len(columns),
        completed_at=completed_at,
    )
    await db_session.flush()
    return job.id


@pytest.mark.asyncio
async def test_completed_dataset_listing_excludes_incomplete_jobs(db_session: AsyncSession) -> None:
    repository = DatasetDiscoveryRepository(db_session)

    job_id = await _create_job(
        db_session,
        status=IngestionStatus.COMPLETED,
        completed_at=datetime(2026, 1, 10, tzinfo=timezone.utc),
        row_count=1,
        rows=[{"row_number": 0, "values": {"name": "one"}}],
    )
    await _create_job(db_session, status=IngestionStatus.PENDING, row_count=1)

    total = await repository.count_analytics_ready_datasets()
    assert total == 1

    results = await repository.list_analytics_ready_datasets(limit=10, offset=0)
    assert [entry.job.id for entry in results] == [job_id]


@pytest.mark.asyncio
async def test_database_pagination_and_deterministic_ordering(db_session: AsyncSession) -> None:
    repository = DatasetDiscoveryRepository(db_session)

    older_id = await _create_job(
        db_session,
        status=IngestionStatus.COMPLETED,
        completed_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        row_count=1,
        rows=[{"row_number": 0, "values": {"name": "older"}}],
    )
    newer_id = await _create_job(
        db_session,
        status=IngestionStatus.COMPLETED,
        completed_at=datetime(2026, 1, 2, tzinfo=timezone.utc),
        row_count=1,
        rows=[{"row_number": 0, "values": {"name": "newer"}}],
    )
    page_one = await repository.list_analytics_ready_datasets(limit=1, offset=0)
    page_two = await repository.list_analytics_ready_datasets(limit=1, offset=1)

    assert [entry.job.id for entry in page_one] == [newer_id]
    assert [entry.job.id for entry in page_two] == [older_id]


@pytest.mark.asyncio
async def test_job_with_registry_and_source_metadata_is_loaded(db_session: AsyncSession) -> None:
    repository = DatasetDiscoveryRepository(db_session)
    job_id = await _create_job(
        db_session,
        status=IngestionStatus.COMPLETED,
        completed_at=datetime(2026, 1, 3, tzinfo=timezone.utc),
        row_count=1,
        rows=[{"row_number": 0, "values": {"name": "source"}}],
    )

    entry = await repository.get_job_with_registry_and_source(job_id)
    assert entry is not None
    assert entry.job.id == job_id
    assert entry.dataset_registry.dataset_name.startswith("Repo Dataset")
    assert entry.data_source.name.startswith("Repo Source")


@pytest.mark.asyncio
async def test_preview_rows_are_bounded(db_session: AsyncSession) -> None:
    repository = DatasetDiscoveryRepository(db_session)
    job_id = await _create_job(
        db_session,
        status=IngestionStatus.COMPLETED,
        completed_at=datetime(2026, 1, 4, tzinfo=timezone.utc),
        row_count=5,
        rows=[{"row_number": i, "values": {"name": f"r{i}"}} for i in range(5)],
    )

    rows = await repository.preview_rows(job_id, limit=2)
    assert len(rows) == 2
    assert [row.row_number for row in rows] == [0, 1]


def test_repository_is_read_only_and_uses_sqlalchemy_expressions_only() -> None:
    source = inspect.getsource(DatasetDiscoveryRepository)
    assert "commit" not in source
    assert "rollback" not in source
    assert "text(" not in source
    assert "delete" not in source
