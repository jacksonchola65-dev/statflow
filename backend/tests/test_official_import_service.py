"""Tests for the official import orchestration foundation."""

from __future__ import annotations

import sys
import uuid

if sys.platform == "win32":
    import asyncio as _asyncio
    _asyncio.set_event_loop_policy(_asyncio.WindowsSelectorEventLoopPolicy())

from dataclasses import dataclass
from typing import Optional

from app.models.data_source import DatasetRegistry, FileFormat, SourceType
from app.models.ingestion import IngestionStatus
from app.repositories.data_source_repository import DataSourceRepository
from app.repositories.dataset_registry_repository import DatasetRegistryRepository
from app.services.official_import_service import (
    ImportData,
    ImportResult,
    ImportSource,
    OfficialDataImporter,
    OfficialImportError,
    OfficialImportService,
    import_data as import_data_wrapper,
)
from app.services.ingestion_persistence_service import (
    IngestionPersistenceResult,
)
from app.services.ingestion_profiling_service import (
    IngestionProfileResult,
    ProfiledColumn,
    ProfiledRow,
    InferredColumnType,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

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
        row_count=2,
        column_count=2,
        columns=[
            ProfiledColumn(
                ordinal_position=0,
                original_name="Province",
                normalized_name="province",
                inferred_type=InferredColumnType.TEXT,
                nullable=False,
                missing_count=0,
                unique_count=2,
                sample_values=["Lusaka", "Copperbelt"],
            ),
            ProfiledColumn(
                ordinal_position=1,
                original_name="Value",
                normalized_name="value",
                inferred_type=InferredColumnType.INTEGER,
                nullable=False,
                missing_count=0,
                unique_count=2,
                sample_values=["100", "120"],
            ),
        ],
        rows=[
            ProfiledRow(row_number=0, values={"province": "Lusaka", "value": "100"}),
            ProfiledRow(row_number=1, values={"province": "Copperbelt", "value": "120"}),
        ],
    )


class DummyImporter(OfficialDataImporter):
    def __init__(self, data: ImportData | Exception):
        self._data = data

    async def import_data(self) -> ImportData:
        if isinstance(self._data, Exception):
            raise self._data
        return self._data


@dataclass
class StubProfilingService:
    profile_called_with: list[tuple[str, bytes]] = None
    profile_result: IngestionProfileResult = None

    def __post_init__(self):
        self.profile_called_with = []

    def profile_dataset(self, *, filename: str, content: bytes) -> IngestionProfileResult:
        self.profile_called_with.append((filename, content))
        return self.profile_result


@dataclass
class StubPersistenceService:
    persist_called_with: list[tuple] = None
    persist_result: IngestionPersistenceResult = None

    def __post_init__(self):
        self.persist_called_with = []

    async def persist_profile(
        self,
        *,
        profile: IngestionProfileResult,
        dataset_registry: DatasetRegistry,
        source_type: str,
        source_reference: Optional[str] = None,
        created_by_user_id: Optional[uuid.UUID] = None,
    ) -> IngestionPersistenceResult:
        self.persist_called_with.append(
            (
                profile,
                dataset_registry,
                source_type,
                source_reference,
                created_by_user_id,
            )
        )
        return self.persist_result


# ===========================================================================
# Tests
# ===========================================================================

async def test_official_import_service_orchestrates_profile_and_persistence(db_session):
    registry = await _make_registry(db_session)
    profile = _make_profile()
    persist_result = IngestionPersistenceResult(
        ingestion_job_id=uuid.uuid4(),
        columns_inserted=2,
        rows_inserted=2,
        final_status=IngestionStatus.COMPLETED,
    )

    profiling_stub = StubProfilingService(profile_result=profile)
    persistence_stub = StubPersistenceService(persist_result=persist_result)

    importer_data = ImportData(
        source=ImportSource.ZAMSTATS,
        original_filename="official.csv",
        content=b"province,value\nLusaka,100\nCopperbelt,120\n",
        source_reference="https://example.com/official.csv",
    )
    importer = DummyImporter(importer_data)

    service = OfficialImportService(
        db_session,
        profiling_service=profiling_stub,
        persistence_service=persistence_stub,
    )

    created_by_user_id = uuid.uuid4()
    result = await service.import_data(
        importer=importer,
        dataset_registry=registry,
        created_by_user_id=created_by_user_id,
    )

    assert result.ingestion_job_id == persist_result.ingestion_job_id
    assert result.source == ImportSource.ZAMSTATS
    assert result.original_filename == "official.csv"
    assert result.rows_imported == 2
    assert result.columns_imported == 2
    assert result.final_status == IngestionStatus.COMPLETED

    assert profiling_stub.profile_called_with == [
        ("official.csv", importer_data.content),
    ]
    assert persistence_stub.persist_called_with == [
        (
            profile,
            registry,
            "zamstats",
            "https://example.com/official.csv",
            created_by_user_id,
        )
    ]


async def test_official_import_service_raises_official_import_error_for_importer_failure(db_session):
    registry = await _make_registry(db_session)
    importer = DummyImporter(RuntimeError("network failure"))

    service = OfficialImportService(db_session)

    try:
        await service.import_data(importer=importer, dataset_registry=registry)
        raise AssertionError("Expected OfficialImportError")
    except OfficialImportError as exc:
        assert "Official importer failed to retrieve dataset" in str(exc)


async def test_import_data_wrapper_delegates_to_service(monkeypatch, db_session):
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
                content=b"province,value\nLusaka,100\n",
            )

    registry = await _make_registry(db_session)
    result = await import_data_wrapper(
        db_session,
        importer=SimpleImporter(),
        dataset_registry=registry,
        created_by_user_id=uuid.uuid4(),
    )

    assert result.source == ImportSource.PACRA
    assert result.original_filename == "delegate.csv"
    assert result.rows_imported == 1
    assert result.columns_imported == 1
    assert result.final_status == IngestionStatus.COMPLETED
