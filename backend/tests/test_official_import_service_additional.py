"""Additional focused tests for OfficialImportService orchestration and error handling."""

from __future__ import annotations

import asyncio
import sys
import uuid

if sys.platform == "win32":
    import asyncio as _asyncio

    _asyncio.set_event_loop_policy(_asyncio.WindowsSelectorEventLoopPolicy())

from dataclasses import dataclass
from typing import Optional

import pytest
from app.models.data_source import DatasetRegistry, FileFormat, SourceType
from app.models.ingestion import IngestionStatus
from app.repositories.data_source_repository import DataSourceRepository
from app.repositories.dataset_registry_repository import DatasetRegistryRepository
from app.services.ingestion_persistence_service import (
    IngestionPersistenceError,
    IngestionPersistenceResult,
)
from app.services.ingestion_profiling_service import (
    InferredColumnType,
    IngestionProfileResult,
    IngestionProfilingError,
    ProfiledColumn,
    ProfiledRow,
)
from app.services.official_import_service import (
    ImportData,
    ImportResult,
    ImportSource,
    OfficialDataImporter,
    OfficialImportError,
    OfficialImportService,
)
from app.services.official_import_service import (
    import_data as import_data_wrapper,
)


async def _make_registry(db_session) -> DatasetRegistry:
    ds_repo = DataSourceRepository(db_session)
    ds = await ds_repo.create(
        name=f"Official Import Source {uuid.uuid4().hex[:6]}",
        is_active=True,
    )
    await db_session.flush()

    reg_repo = DatasetRegistryRepository(db_session)
    registry = await reg_repo.create(
        data_source_id=ds.id,
        dataset_name=f"Official Import Dataset {uuid.uuid4().hex[:6]}",
        source_type=SourceType.OFFICIAL,
        file_format=FileFormat.CSV,
    )
    await db_session.flush()
    return registry


def _make_profile() -> IngestionProfileResult:
    return IngestionProfileResult(
        original_filename="official.csv",
        detected_file_format=FileFormat.CSV,
        worksheet_name=None,
        row_count=1,
        column_count=1,
        columns=[
            ProfiledColumn(
                ordinal_position=0,
                original_name="Value",
                normalized_name="value",
                inferred_type=InferredColumnType.INTEGER,
                nullable=False,
                missing_count=0,
                unique_count=1,
                sample_values=["100"],
            )
        ],
        rows=[ProfiledRow(row_number=0, values={"value": "100"})],
    )


class CountingImporter(OfficialDataImporter):
    def __init__(self, data: ImportData | Exception):
        self._data = data
        self.calls = 0

    async def import_data(self) -> ImportData:
        self.calls += 1
        if isinstance(self._data, Exception):
            raise self._data
        return self._data


@dataclass
class EventRecorder:
    events: list = None

    def __post_init__(self):
        self.events = []


@dataclass
class StubProfiling:
    recorder: EventRecorder
    result: IngestionProfileResult | None = None
    calls: int = 0

    def profile_dataset(self, *, filename: str, content: bytes) -> IngestionProfileResult:
        self.calls += 1
        self.recorder.events.append("profile")
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


@dataclass
class StubPersistence:
    recorder: EventRecorder
    result: Optional[IngestionPersistenceResult] = None
    calls: int = 0

    async def persist_profile(
        self,
        *,
        profile: IngestionProfileResult,
        dataset_registry: DatasetRegistry,
        source_type: str,
        source_reference: Optional[str] = None,
        created_by_user_id: Optional[uuid.UUID] = None,
    ) -> IngestionPersistenceResult:
        self.calls += 1
        self.recorder.events.append("persist")
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


async def test_each_component_called_once_and_in_order(db_session):
    registry = await _make_registry(db_session)

    profile = _make_profile()
    persist_res = IngestionPersistenceResult(
        ingestion_job_id=uuid.uuid4(),
        columns_inserted=1,
        rows_inserted=1,
        final_status=IngestionStatus.COMPLETED,
    )

    events = EventRecorder()
    importer_data = ImportData(
        source=ImportSource.ZAMSTATS,
        original_filename="official.csv",
        content=b"value\n100\n",
    )
    importer = CountingImporter(importer_data)
    profiling = StubProfiling(recorder=events, result=profile)
    persistence = StubPersistence(recorder=events, result=persist_res)

    service = OfficialImportService(
        db_session,
        profiling_service=profiling,
        persistence_service=persistence,
    )

    result = await service.import_data(importer=importer, dataset_registry=registry)

    assert importer.calls == 1
    assert profiling.calls == 1
    assert persistence.calls == 1
    assert events.events == ["profile", "persist"]

    assert result.ingestion_job_id == persist_res.ingestion_job_id


async def test_profiling_exception_propagates(db_session):
    registry = await _make_registry(db_session)
    importer_data = ImportData(
        source=ImportSource.ZAMSTATS,
        original_filename="official.csv",
        content=b"value\n100\n",
    )
    importer = CountingImporter(importer_data)

    profiling = StubProfiling(recorder=EventRecorder(), result=IngestionProfilingError("bad data"))
    persistence = StubPersistence(recorder=EventRecorder(), result=None)

    service = OfficialImportService(
        db_session, profiling_service=profiling, persistence_service=persistence
    )

    with pytest.raises(IngestionProfilingError):
        await service.import_data(importer=importer, dataset_registry=registry)


async def test_persistence_exception_propagates(db_session):
    registry = await _make_registry(db_session)
    importer_data = ImportData(
        source=ImportSource.ZAMSTATS,
        original_filename="official.csv",
        content=b"value\n100\n",
    )
    importer = CountingImporter(importer_data)

    profiling = StubProfiling(recorder=EventRecorder(), result=_make_profile())
    persistence = StubPersistence(
        recorder=EventRecorder(), result=IngestionPersistenceError("db fail")
    )

    service = OfficialImportService(
        db_session, profiling_service=profiling, persistence_service=persistence
    )

    with pytest.raises(IngestionPersistenceError):
        await service.import_data(importer=importer, dataset_registry=registry)


async def test_importer_exception_wrapped(db_session):
    registry = await _make_registry(db_session)
    importer = CountingImporter(RuntimeError("net"))
    service = OfficialImportService(db_session)

    with pytest.raises(OfficialImportError) as excinfo:
        await service.import_data(importer=importer, dataset_registry=registry)
    assert isinstance(excinfo.value.__cause__, RuntimeError)


async def test_cancellederror_propagates(db_session):
    registry = await _make_registry(db_session)

    class CancelImporter(OfficialDataImporter):
        async def import_data(self) -> ImportData:
            raise asyncio.CancelledError()

    service = OfficialImportService(db_session)

    with pytest.raises(asyncio.CancelledError):
        await service.import_data(importer=CancelImporter(), dataset_registry=registry)


def test_no_repository_imports_in_module():
    # Assert source file does not import app.repositories to guard architecture
    import inspect

    import app.services.official_import_service as mod

    src = inspect.getsource(mod)
    assert "from app.repositories" not in src


async def test_import_data_wrapper_delegates(monkeypatch, db_session):
    class FakeService:
        def __init__(self, session):
            assert session is db_session

        async def import_data(self, importer, dataset_registry, *, created_by_user_id=None):
            return ImportResult(
                ingestion_job_id=uuid.uuid4(),
                source=ImportSource.PACRA,
                original_filename="delegate.csv",
                rows_imported=1,
                columns_imported=1,
                final_status=IngestionStatus.COMPLETED,
            )

    monkeypatch.setattr(
        "app.services.official_import_service.OfficialImportService",
        FakeService,
    )

    @dataclass
    class SimpleImporter(OfficialDataImporter):
        async def import_data(self) -> ImportData:
            return ImportData(
                source=ImportSource.PACRA,
                original_filename="delegate.csv",
                content=b"value\n1\n",
            )

    registry = await _make_registry(db_session)
    result = await import_data_wrapper(
        db_session, importer=SimpleImporter(), dataset_registry=registry
    )

    assert result.source == ImportSource.PACRA
    assert result.original_filename == "delegate.csv"
