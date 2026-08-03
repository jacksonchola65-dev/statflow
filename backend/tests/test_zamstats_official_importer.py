from __future__ import annotations

import asyncio
import sys
from typing import Optional

import pytest
from app.models.data_source import DatasetRegistry, FileFormat, SourceType
from app.models.ingestion import IngestionStatus
from app.repositories.data_source_repository import DataSourceRepository
from app.repositories.dataset_registry_repository import DatasetRegistryRepository
from app.services.http_official_data_importer import (
    HttpImportError,
    HttpOfficialImportConfig,
)
from app.services.ingestion_persistence_service import IngestionPersistenceResult
from app.services.ingestion_profiling_service import IngestionProfileResult
from app.services.official_import_service import (
    ImportData,
    ImportSource,
    OfficialImportService,
)
from app.services.zamstats_official_importer import ZamstatsOfficialDataImporter

if sys.platform == "win32":
    import asyncio as _asyncio

    _asyncio.set_event_loop_policy(_asyncio.WindowsSelectorEventLoopPolicy())


class FakeAdapter:
    def __init__(self, result: ImportData | None = None, exc: Exception | None = None) -> None:
        self._result = result
        self._exc = exc
        self.calls = 0

    async def import_data(self) -> ImportData:
        self.calls += 1
        if self._exc is not None:
            raise self._exc
        if self._result is None:
            raise AssertionError("No result configured")
        return self._result


async def _make_registry(db_session) -> DatasetRegistry:
    ds_repo = DataSourceRepository(db_session)
    ds = await ds_repo.create(name="ZAMSTATS test source", is_active=True)
    await db_session.flush()

    reg_repo = DatasetRegistryRepository(db_session)
    registry = await reg_repo.create(
        data_source_id=ds.id,
        dataset_name="ZAMSTATS test dataset",
        source_type=SourceType.OFFICIAL,
        file_format=FileFormat.CSV,
    )
    await db_session.flush()
    return registry


@pytest.mark.asyncio
async def test_zamstats_importer_satisfies_official_contract():
    expected = ImportData(
        source=ImportSource.ZAMSTATS,
        original_filename="zamstats.csv",
        content=b"province,value\nLusaka,100\n",
        source_reference="https://example.org/source",
    )
    adapter = FakeAdapter(result=expected)
    importer = ZamstatsOfficialDataImporter(adapter=adapter)

    result = await importer.import_data()

    assert result == expected
    assert adapter.calls == 1


@pytest.mark.asyncio
async def test_zamstats_importer_uses_http_adapter_configuration(monkeypatch):
    captured = {}

    class RecordingAdapter:
        def __init__(self, config: HttpOfficialImportConfig):
            captured["config"] = config

        async def import_data(self) -> ImportData:
            return ImportData(
                source=ImportSource.ZAMSTATS,
                original_filename="configured.csv",
                content=b"ok",
            )

    monkeypatch.setattr(
        "app.services.zamstats_official_importer.HttpOfficialDataImporter",
        RecordingAdapter,
    )

    importer = ZamstatsOfficialDataImporter(url="https://example.org/data.csv")
    result = await importer.import_data()

    config = captured["config"]
    assert config.source == ImportSource.ZAMSTATS
    assert config.url.startswith("https://")
    assert config.allowed_content_types is not None
    assert "text/csv" in config.allowed_content_types
    assert config.timeout_seconds > 0
    assert config.maximum_response_bytes > 0
    assert result.original_filename == "configured.csv"


@pytest.mark.asyncio
async def test_missing_url_configuration_fails_clearly(monkeypatch):
    monkeypatch.setattr(
        "app.services.zamstats_official_importer.settings.ZAMSTATS_DATASET_URL", None
    )
    importer = ZamstatsOfficialDataImporter()

    with pytest.raises(ValueError, match="must be configured"):
        await importer.import_data()


@pytest.mark.asyncio
async def test_http_adapter_exception_propagates_unchanged():
    expected = HttpImportError("adapter failed")
    adapter = FakeAdapter(exc=expected)
    importer = ZamstatsOfficialDataImporter(adapter=adapter)

    with pytest.raises(HttpImportError) as excinfo:
        await importer.import_data()

    assert excinfo.value is expected


@pytest.mark.asyncio
async def test_cancellation_propagates_unchanged():
    adapter = FakeAdapter(exc=asyncio.CancelledError())
    importer = ZamstatsOfficialDataImporter(adapter=adapter)

    with pytest.raises(asyncio.CancelledError):
        await importer.import_data()


@pytest.mark.asyncio
async def test_zamstats_importer_works_with_official_import_service(db_session):
    class StubProfilingService:
        def profile_dataset(self, *, filename: str, content: bytes) -> IngestionProfileResult:
            return IngestionProfileResult(
                original_filename=filename,
                detected_file_format=FileFormat.CSV,
                worksheet_name=None,
                row_count=1,
                column_count=1,
                columns=[],
                rows=[],
            )

    class StubPersistenceService:
        async def persist_profile(
            self,
            *,
            profile: IngestionProfileResult,
            dataset_registry: DatasetRegistry,
            source_type: str,
            source_reference: Optional[str] = None,
            created_by_user_id: Optional[object] = None,
        ) -> IngestionPersistenceResult:
            return IngestionPersistenceResult(
                ingestion_job_id=object(),
                columns_inserted=0,
                rows_inserted=0,
                final_status=IngestionStatus.COMPLETED,
            )

    importer = ZamstatsOfficialDataImporter(
        adapter=FakeAdapter(
            result=ImportData(
                source=ImportSource.ZAMSTATS,
                original_filename="zamstats.csv",
                content=b"value\n1\n",
                source_reference="https://example.org/source",
            )
        )
    )
    service = OfficialImportService(
        db_session,
        profiling_service=StubProfilingService(),
        persistence_service=StubPersistenceService(),
    )
    registry = await _make_registry(db_session)

    result = await service.import_data(importer=importer, dataset_registry=registry)

    assert result.source == ImportSource.ZAMSTATS
    assert result.original_filename == "zamstats.csv"
    assert result.final_status == IngestionStatus.COMPLETED
