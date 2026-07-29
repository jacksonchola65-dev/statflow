from __future__ import annotations

import asyncio
import sys
import uuid
from dataclasses import dataclass
from typing import Optional

import httpx
import pytest

from app.models.data_source import DatasetRegistry, FileFormat, SourceType
from app.models.ingestion import IngestionStatus
from app.repositories.data_source_repository import DataSourceRepository
from app.repositories.dataset_column_repository import DatasetColumnRepository
from app.repositories.dataset_registry_repository import DatasetRegistryRepository
from app.repositories.dataset_row_repository import DatasetRowRepository
from app.repositories.ingestion_job_repository import IngestionJobRepository
from app.services.http_official_data_importer import (
    HttpImportError,
    HttpOfficialDataImporter,
    HttpOfficialImportConfig,
)
from app.services.ingestion_inspection_service import IngestionInspectionService
from app.services.ingestion_persistence_service import (
    IngestionPersistenceError,
    IngestionPersistenceService,
)
from app.services.ingestion_profiling_service import IngestionProfilingService
from app.services.official_import_service import (
    ImportData,
    ImportSource,
    OfficialImportError,
    OfficialImportService,
)
from app.services.zamstats_official_importer import ZamstatsOfficialDataImporter


if sys.platform == "win32":
    import asyncio as _asyncio

    _asyncio.set_event_loop_policy(_asyncio.WindowsSelectorEventLoopPolicy())


async def _make_registry(db_session) -> DatasetRegistry:
    ds_repo = DataSourceRepository(db_session)
    ds = await ds_repo.create(name="Execution Test Source", is_active=True)
    await db_session.flush()

    reg_repo = DatasetRegistryRepository(db_session)
    registry = await reg_repo.create(
        data_source_id=ds.id,
        dataset_name="Execution Test Dataset",
        source_type=SourceType.OFFICIAL,
        file_format=FileFormat.CSV,
    )
    await db_session.flush()
    return registry


@pytest.mark.asyncio
async def test_end_to_end_official_import_executes_and_is_inspectable(db_session):
    dataset_bytes = b"province,district,population\nLuapula,Mansa,327063\nLusaka,Lusaka,2746407\nCopperbelt,Kitwe,661901\n"

    async def handler(request):
        return httpx.Response(
            200,
            headers={"content-type": "text/csv; charset=utf-8"},
            content=dataset_bytes,
        )

    http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    adapter = HttpOfficialDataImporter(
        config=HttpOfficialImportConfig(
            source=ImportSource.ZAMSTATS,
            url="https://example.com/zamstats.csv",
            original_filename="zamstats.csv",
            source_reference="https://example.org/source",
            timeout_seconds=2.0,
            maximum_response_bytes=1024 * 1024,
            allowed_content_types={"text/csv"},
        ),
        client=http_client,
    )
    importer = ZamstatsOfficialDataImporter(adapter=adapter, url="https://example.com/zamstats.csv", source_reference="https://example.org/source")
    service = OfficialImportService(
        db_session,
        profiling_service=IngestionProfilingService(),
        persistence_service=IngestionPersistenceService(db_session),
    )
    registry = await _make_registry(db_session)

    result = await service.import_data(importer=importer, dataset_registry=registry, created_by_user_id=None)

    assert result.source == ImportSource.ZAMSTATS
    assert result.original_filename == "zamstats.csv"
    assert result.rows_imported == 3
    assert result.columns_imported == 3
    assert result.final_status == IngestionStatus.COMPLETED

    inspection = await IngestionInspectionService(db_session).get_inspection(result.ingestion_job_id)
    assert inspection.job.id == result.ingestion_job_id
    assert inspection.job.original_filename == "zamstats.csv"
    assert len(inspection.columns) == 3
    assert len(inspection.rows) == 3
    assert inspection.pagination.total_items == 3

    assert not http_client.is_closed


@pytest.mark.asyncio
async def test_download_failure_leaves_no_persisted_data(db_session):
    async def handler(request):
        raise httpx.ConnectError("boom")

    http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    adapter = HttpOfficialDataImporter(
        config=HttpOfficialImportConfig(
            source=ImportSource.ZAMSTATS,
            url="https://example.com/zamstats.csv",
            original_filename="zamstats.csv",
            timeout_seconds=2.0,
            maximum_response_bytes=1024 * 1024,
        ),
        client=http_client,
    )
    importer = ZamstatsOfficialDataImporter(adapter=adapter, url="https://example.com/zamstats.csv")
    service = OfficialImportService(db_session, profiling_service=IngestionProfilingService(), persistence_service=IngestionPersistenceService(db_session))
    registry = await _make_registry(db_session)

    with pytest.raises(OfficialImportError):
        await service.import_data(importer=importer, dataset_registry=registry)

    inspection_service = IngestionInspectionService(db_session)
    with pytest.raises(Exception):
        await inspection_service.get_inspection(uuid.uuid4())


@pytest.mark.asyncio
async def test_profiling_failure_leaves_no_persisted_data(db_session):
    class FailingProfilingService:
        def profile_dataset(self, *, filename: str, content: bytes):
            raise RuntimeError("boom")

    importer = ZamstatsOfficialDataImporter(
        adapter=FakeAdapter(result=ImportData(source=ImportSource.ZAMSTATS, original_filename="zamstats.csv", content=b"value\n1\n")),
        url="https://example.org/zamstats.csv",
    )
    service = OfficialImportService(db_session, profiling_service=FailingProfilingService(), persistence_service=IngestionPersistenceService(db_session))
    registry = await _make_registry(db_session)

    with pytest.raises(RuntimeError):
        await service.import_data(importer=importer, dataset_registry=registry)


@pytest.mark.asyncio
async def test_cancellation_during_download_propagates(db_session):
    class CancelAdapter:
        async def import_data(self) -> ImportData:
            raise asyncio.CancelledError()

    importer = ZamstatsOfficialDataImporter(adapter=CancelAdapter(), url="https://example.org/zamstats.csv")
    service = OfficialImportService(db_session, profiling_service=IngestionProfilingService(), persistence_service=IngestionPersistenceService(db_session))
    registry = await _make_registry(db_session)

    with pytest.raises(asyncio.CancelledError):
        await service.import_data(importer=importer, dataset_registry=registry)


@pytest.mark.asyncio
async def test_persistence_failure_rolls_back_partial_state(db_session, monkeypatch):
    created_job_ids = []
    original_create = IngestionJobRepository.create

    async def tracking_create(self, **kwargs):
        job = await original_create(self, **kwargs)
        created_job_ids.append(job.id)
        return job

    monkeypatch.setattr(IngestionJobRepository, "create", tracking_create)

    async def failing_create_many(self, rows):
        raise RuntimeError("simulated persistence failure")

    monkeypatch.setattr(DatasetRowRepository, "create_many", failing_create_many)

    importer = ZamstatsOfficialDataImporter(
        adapter=FakeAdapter(
            result=ImportData(
                source=ImportSource.ZAMSTATS,
                original_filename="zamstats.csv",
                content=b"province,district,population\nLuapula,Mansa,327063\n",
            )
        ),
        url="https://example.org/zamstats.csv",
    )
    service = OfficialImportService(
        db_session,
        profiling_service=IngestionProfilingService(),
        persistence_service=IngestionPersistenceService(db_session),
    )
    registry = await _make_registry(db_session)

    with pytest.raises(IngestionPersistenceError):
        await service.import_data(importer=importer, dataset_registry=registry)

    job_repo = IngestionJobRepository(db_session)
    assert created_job_ids
    job_id = created_job_ids[0]
    assert await job_repo.get_by_id(job_id) is None

    column_repo = DatasetColumnRepository(db_session)
    assert await column_repo.list_by_ingestion_job(job_id) == []

    row_repo = DatasetRowRepository(db_session)
    assert await row_repo.count_for_job(job_id) == 0

    inspection_service = IngestionInspectionService(db_session)
    with pytest.raises(Exception):
        await inspection_service.get_inspection(job_id)


@pytest.mark.asyncio
async def test_cancellation_during_profiling_propagates_and_leaves_no_persisted_state(db_session):
    class FailingProfilingService:
        def profile_dataset(self, *, filename: str, content: bytes):
            raise asyncio.CancelledError()

    class RecordingPersistenceService:
        def __init__(self) -> None:
            self.calls = 0

        async def persist_profile(self, **kwargs):
            self.calls += 1
            raise AssertionError("persistence should not be called")

    importer = ZamstatsOfficialDataImporter(
        adapter=FakeAdapter(
            result=ImportData(
                source=ImportSource.ZAMSTATS,
                original_filename="zamstats.csv",
                content=b"province,district,population\nLuapula,Mansa,327063\n",
            )
        ),
        url="https://example.org/zamstats.csv",
    )
    persistence_service = RecordingPersistenceService()
    service = OfficialImportService(
        db_session,
        profiling_service=FailingProfilingService(),
        persistence_service=persistence_service,
    )
    registry = await _make_registry(db_session)

    with pytest.raises(asyncio.CancelledError):
        await service.import_data(importer=importer, dataset_registry=registry)

    assert persistence_service.calls == 0
    assert len(await IngestionJobRepository(db_session).list_by_dataset_registry(registry.id)) == 0


@pytest.mark.asyncio
async def test_cancellation_during_persistence_rolls_back_partial_state(db_session, monkeypatch):
    created_job_ids = []
    original_create = IngestionJobRepository.create

    async def tracking_create(self, **kwargs):
        job = await original_create(self, **kwargs)
        created_job_ids.append(job.id)
        return job

    monkeypatch.setattr(IngestionJobRepository, "create", tracking_create)

    async def failing_create_many(self, rows):
        raise asyncio.CancelledError()

    monkeypatch.setattr(DatasetRowRepository, "create_many", failing_create_many)

    importer = ZamstatsOfficialDataImporter(
        adapter=FakeAdapter(
            result=ImportData(
                source=ImportSource.ZAMSTATS,
                original_filename="zamstats.csv",
                content=b"province,district,population\nLuapula,Mansa,327063\n",
            )
        ),
        url="https://example.org/zamstats.csv",
    )
    service = OfficialImportService(
        db_session,
        profiling_service=IngestionProfilingService(),
        persistence_service=IngestionPersistenceService(db_session),
    )
    registry = await _make_registry(db_session)

    with pytest.raises(asyncio.CancelledError):
        await service.import_data(importer=importer, dataset_registry=registry)

    job_repo = IngestionJobRepository(db_session)
    assert created_job_ids
    job_id = created_job_ids[0]
    assert await job_repo.get_by_id(job_id) is None
    assert await DatasetColumnRepository(db_session).list_by_ingestion_job(job_id) == []
    assert await DatasetRowRepository(db_session).count_for_job(job_id) == 0


@pytest.mark.asyncio
async def test_duplicate_import_creates_two_independent_ingestion_jobs(db_session):
    importer = ZamstatsOfficialDataImporter(
        adapter=FakeAdapter(
            result=ImportData(
                source=ImportSource.ZAMSTATS,
                original_filename="zamstats.csv",
                content=b"province,district,population\nLuapula,Mansa,327063\n",
            )
        ),
        url="https://example.org/zamstats.csv",
    )
    service = OfficialImportService(
        db_session,
        profiling_service=IngestionProfilingService(),
        persistence_service=IngestionPersistenceService(db_session),
    )
    registry = await _make_registry(db_session)

    first_result = await service.import_data(importer=importer, dataset_registry=registry)
    second_result = await service.import_data(importer=importer, dataset_registry=registry)

    job_repo = IngestionJobRepository(db_session)
    jobs = await job_repo.list_by_dataset_registry(registry.id)
    assert len(jobs) == 2
    assert first_result.ingestion_job_id != second_result.ingestion_job_id


class FakeAdapter:
    def __init__(self, result: ImportData | None = None, exc: Exception | None = None) -> None:
        self._result = result
        self._exc = exc

    async def import_data(self) -> ImportData:
        if self._exc is not None:
            raise self._exc
        return self._result
