from __future__ import annotations

import asyncio
import inspect
import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.domain.analytics.compatibility import supported_aggregations
from app.domain.analytics.discovery import (
    DatasetDiscoveryRepository,
    DatasetDiscoveryService,
)
from app.domain.analytics.exceptions import (
    IncompleteIngestionJobError,
    UnknownIngestionJobError,
)
from app.domain.analytics.planner import AnalyticsQueryPlanner
from app.domain.analytics.contracts import (
    AggregationFunction,
    AnalyticsQuery,
    DatasetReference,
    Dimension,
    Measure,
)
from app.models.data_source import FileFormat, SourceType
from app.models.ingestion import IngestionStatus, InferredColumnType
from app.repositories.data_source_repository import DataSourceRepository
from app.repositories.dataset_column_repository import DatasetColumnRepository
from app.repositories.dataset_registry_repository import DatasetRegistryRepository
from app.repositories.dataset_row_repository import DatasetRowRepository
from app.repositories.ingestion_job_repository import IngestionJobRepository


async def _create_dataset(
    db_session: AsyncSession,
    *,
    status: IngestionStatus = IngestionStatus.COMPLETED,
    completed_at: datetime | None = None,
    row_count: int = 2,
    column_specs: list[dict] | None = None,
    rows: list[dict] | None = None,
) -> IngestionJob:
    data_source = await DataSourceRepository(db_session).create(
        name=f"Discovery Source {uuid.uuid4().hex[:8]}",
        is_active=True,
    )
    await db_session.flush()

    registry = await DatasetRegistryRepository(db_session).create(
        data_source_id=data_source.id,
        dataset_name=f"Discovery Dataset {uuid.uuid4().hex[:8]}",
        source_type=SourceType.OFFICIAL,
        file_format=FileFormat.CSV,
    )
    await db_session.flush()

    job = await IngestionJobRepository(db_session).create(
        dataset_registry_id=registry.id,
        original_filename="discovery.csv",
        file_format=FileFormat.CSV,
        file_size_bytes=128,
        status=status,
    )
    await db_session.flush()

    if column_specs is None:
        column_specs = [
            {
                "ordinal_position": 0,
                "original_name": "Region",
                "normalized_name": "region",
                "inferred_type": InferredColumnType.TEXT,
                "nullable": False,
                "missing_count": 0,
                "unique_count": 2,
                "sample_values": ["North", "South"],
            },
            {
                "ordinal_position": 1,
                "original_name": "Population",
                "normalized_name": "population",
                "inferred_type": InferredColumnType.INTEGER,
                "nullable": False,
                "missing_count": 0,
                "unique_count": 2,
                "sample_values": ["100", "200"],
            },
        ]

    for spec in column_specs:
        spec["ingestion_job_id"] = job.id

    await DatasetColumnRepository(db_session).create_many(column_specs)

    if rows is None:
        rows = [
            {
                "row_number": 0,
                "values": {"region": "North", "population": 100},
            },
            {
                "row_number": 1,
                "values": {"region": "South", "population": 200},
            },
        ]

    for row in rows:
        row["ingestion_job_id"] = job.id

    if rows:
        await DatasetRowRepository(db_session).create_many(rows)

    await IngestionJobRepository(db_session).update(
        job.id,
        status=status,
        row_count=row_count if status == IngestionStatus.COMPLETED else row_count,
        column_count=len(column_specs),
        completed_at=completed_at or (datetime.now(timezone.utc) if status == IngestionStatus.COMPLETED else None),
    )
    await db_session.flush()
    return job


@pytest.mark.asyncio
async def test_list_datasets_returns_only_analytics_ready_jobs(db_session: AsyncSession) -> None:
    completed_job = await _create_dataset(db_session, status=IngestionStatus.COMPLETED)
    await _create_dataset(db_session, status=IngestionStatus.PENDING)
    repository = DatasetDiscoveryRepository(db_session)
    service = DatasetDiscoveryService(repository)

    result = await service.list_datasets(limit=10, offset=0)

    assert result.total == 1
    assert len(result.items) == 1
    assert result.items[0].ingestion_job_id == completed_job.id
    assert result.has_more is False


@pytest.mark.asyncio
async def test_list_datasets_pagination_is_stable(db_session: AsyncSession) -> None:
    first_completed_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
    second_completed_at = datetime(2026, 1, 2, tzinfo=timezone.utc)
    older_job = await _create_dataset(
        db_session,
        status=IngestionStatus.COMPLETED,
        completed_at=first_completed_at,
    )
    newer_job = await _create_dataset(
        db_session,
        status=IngestionStatus.COMPLETED,
        completed_at=second_completed_at,
    )

    repository = DatasetDiscoveryRepository(db_session)
    service = DatasetDiscoveryService(repository)

    first_page = await service.list_datasets(limit=1, offset=0)
    second_page = await service.list_datasets(limit=1, offset=1)

    assert first_page.items[0].ingestion_job_id == newer_job.id
    assert second_page.items[0].ingestion_job_id == older_job.id
    assert first_page.has_more is True
    assert second_page.has_more is False


@pytest.mark.asyncio
async def test_get_dataset_details_and_schema_alignment(db_session: AsyncSession) -> None:
    job = await _create_dataset(db_session)
    repository = DatasetDiscoveryRepository(db_session)
    service = DatasetDiscoveryService(repository)

    details = await service.get_dataset_details(job.id)
    assert details.summary.ingestion_job_id == job.id
    assert details.summary.row_count == 2
    assert details.summary.column_count == 2
    assert details.summary.dataset_name.startswith("Discovery Dataset")
    assert details.analytics_ready is True
    assert details.preview_available is True

    assert [column.identifier for column in details.columns] == ["region", "population"]
    assert [column.ordinal_position for column in details.columns] == [0, 1]
    assert details.columns[0].dimension_eligible is True
    assert details.columns[1].measure_eligible is True

    schema = await service.get_schema(job.id)
    assert [column.identifier for column in schema] == ["region", "population"]
    assert [column.ordinal_position for column in schema] == [0, 1]

    assert all(column.__class__.__name__ == "DatasetColumnDescriptor" for column in details.columns)
    assert all(column.identifier in {"region", "population"} for column in details.columns)


@pytest.mark.asyncio
async def test_aggregation_compatibility_policy_is_shared_with_planner(db_session: AsyncSession) -> None:
    job = await _create_dataset(
        db_session,
        column_specs=[
            {
                "ordinal_position": 0,
                "original_name": "Text",
                "normalized_name": "text",
                "inferred_type": InferredColumnType.TEXT,
                "nullable": False,
                "missing_count": 0,
                "unique_count": 2,
                "sample_values": ["a", "b"],
            },
            {
                "ordinal_position": 1,
                "original_name": "Number",
                "normalized_name": "number",
                "inferred_type": InferredColumnType.INTEGER,
                "nullable": False,
                "missing_count": 0,
                "unique_count": 2,
                "sample_values": ["1", "2"],
            },
        ],
        rows=[{"row_number": 0, "values": {"text": "a", "number": 1}}],
        row_count=1,
    )
    planner = AnalyticsQueryPlanner(db_session)

    # Verify every supported aggregation in discovery is accepted by the query planner.
    for column_type, normalized_name in [
        (InferredColumnType.TEXT, "text"),
        (InferredColumnType.INTEGER, "number"),
    ]:
        supported = supported_aggregations(column_type)
        for aggregation in supported:
            measures = [
                Measure(aggregation=aggregation, column_name=normalized_name, alias=f"{normalized_name}_{aggregation.value.lower()}")
            ]
            query = AnalyticsQuery(
                dataset_reference=DatasetReference(ingestion_job_id=job.id),
                dimensions=[],
                measures=measures,
            )
            plan = await planner.plan(query)
            assert plan.ingestion_job_id == job.id


@pytest.mark.asyncio
async def test_dimensions_and_measures_reflect_planner_capabilities(db_session: AsyncSession) -> None:
    job = await _create_dataset(
        db_session,
        column_specs=[
            {
                "ordinal_position": 0,
                "original_name": "Text",
                "normalized_name": "text",
                "inferred_type": InferredColumnType.TEXT,
                "nullable": False,
                "missing_count": 0,
                "unique_count": 2,
                "sample_values": ["a", "b"],
            },
            {
                "ordinal_position": 1,
                "original_name": "Date",
                "normalized_name": "date",
                "inferred_type": InferredColumnType.DATE,
                "nullable": True,
                "missing_count": 0,
                "unique_count": 2,
                "sample_values": ["2026-01-01", "2026-01-02"],
            },
        ],
        rows=[
            {"row_number": 0, "values": {"text": "a", "date": "2026-01-01"}},
        ],
        row_count=1,
    )
    column_repo = DatasetColumnRepository(db_session)
    columns = await column_repo.list_by_ingestion_job(job.id)
    assert len(columns) == 2
    assert {column.normalized_name for column in columns} == {"text", "date"}

    service = DatasetDiscoveryService(DatasetDiscoveryRepository(db_session))
    details = await service.get_dataset_details(job.id)
    dimension_names = {item.identifier for item in details.available_dimensions}
    assert "text" in dimension_names
    assert "date" in dimension_names

    measure_mapping = {item.identifier: item.supported_aggregations for item in details.available_measures}
    assert measure_mapping["text"] == [AggregationFunction.COUNT, AggregationFunction.COUNT_DISTINCT]
    assert measure_mapping["date"] == [AggregationFunction.COUNT, AggregationFunction.COUNT_DISTINCT, AggregationFunction.MINIMUM, AggregationFunction.MAXIMUM]

    planner = AnalyticsQueryPlanner(db_session)
    query = AnalyticsQuery(
        dataset_reference=DatasetReference(ingestion_job_id=job.id),
        dimensions=[Dimension(column_name="text")],
        measures=[
            Measure(aggregation=AggregationFunction.COUNT, alias="row_count"),
            Measure(aggregation=AggregationFunction.MINIMUM, column_name="date", alias="min_date"),
        ],
    )
    plan = await planner.plan(query)
    assert plan.ingestion_job_id == job.id


@pytest.mark.asyncio
async def test_zero_row_completed_dataset_is_discoverable(db_session: AsyncSession) -> None:
    job = await _create_dataset(
        db_session,
        row_count=0,
        rows=[],
        status=IngestionStatus.COMPLETED,
    )
    service = DatasetDiscoveryService(DatasetDiscoveryRepository(db_session))

    details = await service.get_dataset_details(job.id)
    assert details.summary.row_count == 0

    preview = await service.get_preview(job.id, limit=10)
    assert preview.rows == []
    assert preview.returned_count == 0


@pytest.mark.asyncio
async def test_get_preview_limits_default_and_maximum(db_session: AsyncSession) -> None:
    job = await _create_dataset(
        db_session,
        rows=[{"row_number": i, "values": {"region": f"R{i}", "population": i}} for i in range(25)],
        row_count=25,
    )

    service = DatasetDiscoveryService(DatasetDiscoveryRepository(db_session))
    default_preview = await service.get_preview(job.id)
    assert default_preview.limit == 10
    assert default_preview.returned_count == 10

    maximum_preview = await service.get_preview(job.id, limit=50)
    assert maximum_preview.limit == 50
    assert maximum_preview.returned_count == 25


@pytest.mark.asyncio
async def test_get_statistics_from_persisted_metadata(db_session: AsyncSession) -> None:
    job = await _create_dataset(db_session)
    stats = await DatasetDiscoveryService(DatasetDiscoveryRepository(db_session)).get_statistics(job.id)
    assert stats.row_count == 2
    assert stats.column_count == 2
    assert stats.nullable_column_count == 0
    assert stats.numeric_column_count == 1
    assert stats.text_column_count == 1
    assert stats.date_column_count == 0
    assert stats.datetime_column_count == 0
    assert stats.boolean_column_count == 0
    assert stats.completed_at is not None


@pytest.mark.asyncio
async def test_unknown_and_incomplete_dataset_errors(db_session: AsyncSession) -> None:
    service = DatasetDiscoveryService(DatasetDiscoveryRepository(db_session))

    with pytest.raises(UnknownIngestionJobError):
        await service.get_dataset_details(uuid.uuid4())

    incomplete_job = await _create_dataset(db_session, status=IngestionStatus.PENDING)
    with pytest.raises(IncompleteIngestionJobError):
        await service.get_dataset_details(incomplete_job.id)


@pytest.mark.asyncio
async def test_service_propagates_cancellation() -> None:
    class BrokenRepository:
        async def get_job_with_registry_and_source(self, ingestion_job_id):
            raise asyncio.CancelledError()

    service = DatasetDiscoveryService(BrokenRepository())
    with pytest.raises(asyncio.CancelledError):
        await service.get_dataset_details(uuid.uuid4())


def test_service_does_not_import_fastapi() -> None:
    source = inspect.getsource(DatasetDiscoveryService)
    assert "fastapi" not in source


def test_repository_is_read_only_and_uses_sqlalchemy_expressions_only() -> None:
    source = inspect.getsource(DatasetDiscoveryRepository)
    assert "commit" not in source
    assert "rollback" not in source
    assert "text(" not in source
