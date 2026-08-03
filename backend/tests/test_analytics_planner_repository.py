from __future__ import annotations

import inspect

import pytest
from app.domain.analytics import (
    AggregationFunction,
    AnalyticsQuery,
    DatasetReference,
    Dimension,
    FilterClause,
    FilterOperator,
    Measure,
    SortClause,
    SortDirection,
)
from app.domain.analytics.exceptions import (
    InvalidIdentifierError,
)
from app.domain.analytics.metadata import IngestionMetadataResolver
from app.domain.analytics.planner import AnalyticsQueryPlanner
from app.domain.analytics.repository import AnalyticsRepository
from app.models.data_source import FileFormat, SourceType
from app.models.ingestion import InferredColumnType, IngestionJob, IngestionStatus
from app.repositories.data_source_repository import DataSourceRepository
from app.repositories.dataset_column_repository import DatasetColumnRepository
from app.repositories.dataset_registry_repository import DatasetRegistryRepository
from app.repositories.dataset_row_repository import DatasetRowRepository
from app.repositories.ingestion_job_repository import IngestionJobRepository
from pydantic import ValidationError


async def _make_dataset(db_session) -> IngestionJob:
    ds_repo = DataSourceRepository(db_session)
    data_source = await ds_repo.create(name="Analytics Source", is_active=True)
    await db_session.flush()

    reg_repo = DatasetRegistryRepository(db_session)
    registry = await reg_repo.create(
        data_source_id=data_source.id,
        dataset_name="Analytics Dataset",
        source_type=SourceType.OFFICIAL,
        file_format=FileFormat.CSV,
    )
    await db_session.flush()

    job_repo = IngestionJobRepository(db_session)
    job = await job_repo.create(
        dataset_registry_id=registry.id,
        original_filename="analytics.csv",
        file_format=FileFormat.CSV,
        file_size_bytes=128,
        status=IngestionStatus.COMPLETED,
    )

    column_repo = DatasetColumnRepository(db_session)
    await column_repo.create_many(
        [
            {
                "ingestion_job_id": job.id,
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
                "ingestion_job_id": job.id,
                "ordinal_position": 1,
                "original_name": "Population",
                "normalized_name": "population",
                "inferred_type": InferredColumnType.INTEGER,
                "nullable": False,
                "missing_count": 0,
                "unique_count": 2,
                "sample_values": ["100", "200"],
            },
            {
                "ingestion_job_id": job.id,
                "ordinal_position": 2,
                "original_name": "Revenue",
                "normalized_name": "revenue",
                "inferred_type": InferredColumnType.INTEGER,
                "nullable": False,
                "missing_count": 0,
                "unique_count": 2,
                "sample_values": ["10", "20"],
            },
        ]
    )

    row_repo = DatasetRowRepository(db_session)
    await row_repo.create_many(
        [
            {
                "ingestion_job_id": job.id,
                "row_number": 0,
                "values": {"region": "North", "population": 100, "revenue": 10},
            },
            {
                "ingestion_job_id": job.id,
                "row_number": 1,
                "values": {"region": "South", "population": 200, "revenue": 20},
            },
        ]
    )

    await db_session.flush()
    return job


@pytest.mark.asyncio
async def test_planner_builds_execution_plan_from_valid_query(db_session):
    job = await _make_dataset(db_session)
    planner = AnalyticsQueryPlanner(
        db_session, metadata_resolver=IngestionMetadataResolver(db_session)
    )
    query = AnalyticsQuery(
        dataset_reference=DatasetReference(ingestion_job_id=job.id),
        dimensions=[Dimension(column_name="region")],
        measures=[Measure(aggregation=AggregationFunction.COUNT, alias="row_count")],
    )

    plan = await planner.plan(query)

    assert plan.ingestion_job_id == job.id
    assert len(plan.resolved_dimensions) == 1
    assert len(plan.resolved_measures) == 1
    assert plan.limit == 100
    assert plan.offset == 0


@pytest.mark.asyncio
async def test_planner_rejects_unknown_dimension(db_session):
    job = await _make_dataset(db_session)
    planner = AnalyticsQueryPlanner(
        db_session, metadata_resolver=IngestionMetadataResolver(db_session)
    )
    query = AnalyticsQuery(
        dataset_reference=DatasetReference(ingestion_job_id=job.id),
        dimensions=[Dimension(column_name="missing")],
    )

    with pytest.raises(InvalidIdentifierError):
        await planner.plan(query)


@pytest.mark.asyncio
async def test_planner_rejects_unknown_measure(db_session):
    job = await _make_dataset(db_session)
    planner = AnalyticsQueryPlanner(
        db_session, metadata_resolver=IngestionMetadataResolver(db_session)
    )
    query = AnalyticsQuery(
        dataset_reference=DatasetReference(ingestion_job_id=job.id),
        measures=[Measure(aggregation=AggregationFunction.SUM, column_name="missing")],
    )

    with pytest.raises(InvalidIdentifierError):
        await planner.plan(query)


@pytest.mark.asyncio
async def test_planner_rejects_unknown_filter(db_session):
    job = await _make_dataset(db_session)
    planner = AnalyticsQueryPlanner(
        db_session, metadata_resolver=IngestionMetadataResolver(db_session)
    )
    query = AnalyticsQuery(
        dataset_reference=DatasetReference(ingestion_job_id=job.id),
        dimensions=[Dimension(column_name="region")],
        measures=[Measure(aggregation=AggregationFunction.COUNT)],
        filters=[
            FilterClause(column_name="missing", operator=FilterOperator.EQUALS, value="North")
        ],
    )

    with pytest.raises(InvalidIdentifierError):
        await planner.plan(query)


@pytest.mark.asyncio
async def test_planner_rejects_unknown_sort(db_session):
    job = await _make_dataset(db_session)
    with pytest.raises(ValidationError):
        AnalyticsQuery(
            dataset_reference=DatasetReference(ingestion_job_id=job.id),
            dimensions=[Dimension(column_name="region")],
            measures=[Measure(aggregation=AggregationFunction.COUNT, alias="row_count")],
            sorting=[SortClause(target="missing", direction=SortDirection.ASCENDING)],
        )


@pytest.mark.asyncio
async def test_planner_rejects_duplicate_identifiers(db_session):
    job = await _make_dataset(db_session)
    with pytest.raises(ValidationError):
        AnalyticsQuery(
            dataset_reference=DatasetReference(ingestion_job_id=job.id),
            dimensions=[Dimension(column_name="region", alias="shared")],
            measures=[Measure(aggregation=AggregationFunction.COUNT, alias="shared")],
        )


@pytest.mark.asyncio
async def test_planner_resolves_metadata_for_dimensions_and_measures(db_session):
    job = await _make_dataset(db_session)
    planner = AnalyticsQueryPlanner(
        db_session, metadata_resolver=IngestionMetadataResolver(db_session)
    )
    query = AnalyticsQuery(
        dataset_reference=DatasetReference(ingestion_job_id=job.id),
        dimensions=[Dimension(column_name="region")],
        measures=[
            Measure(
                aggregation=AggregationFunction.SUM,
                column_name="population",
                alias="population_sum",
            )
        ],
    )

    plan = await planner.plan(query)

    assert plan.resolved_dimensions[0].metadata.inferred_type == "TEXT"
    assert plan.resolved_measures[0].metadata.inferred_type == "INTEGER"


@pytest.mark.asyncio
async def test_repository_executes_count_and_grouping(db_session):
    job = await _make_dataset(db_session)
    planner = AnalyticsQueryPlanner(
        db_session, metadata_resolver=IngestionMetadataResolver(db_session)
    )
    query = AnalyticsQuery(
        dataset_reference=DatasetReference(ingestion_job_id=job.id),
        dimensions=[Dimension(column_name="region")],
        measures=[Measure(aggregation=AggregationFunction.COUNT, alias="row_count")],
    )
    plan = await planner.plan(query)
    repo = AnalyticsRepository(db_session)

    result = await repo.execute_plan(plan)

    assert result.row_count == 2
    assert result.rows[0]["row_count"] == 1


@pytest.mark.asyncio
async def test_repository_executes_sum_avg_min_max_and_filtering(db_session):
    job = await _make_dataset(db_session)
    planner = AnalyticsQueryPlanner(
        db_session, metadata_resolver=IngestionMetadataResolver(db_session)
    )
    query = AnalyticsQuery(
        dataset_reference=DatasetReference(ingestion_job_id=job.id),
        measures=[
            Measure(
                aggregation=AggregationFunction.SUM,
                column_name="population",
                alias="population_sum",
            ),
            Measure(
                aggregation=AggregationFunction.AVERAGE,
                column_name="population",
                alias="population_avg",
            ),
            Measure(
                aggregation=AggregationFunction.MINIMUM,
                column_name="population",
                alias="population_min",
            ),
            Measure(
                aggregation=AggregationFunction.MAXIMUM,
                column_name="population",
                alias="population_max",
            ),
        ],
        filters=[FilterClause(column_name="region", operator=FilterOperator.EQUALS, value="North")],
    )
    plan = await planner.plan(query)
    repo = AnalyticsRepository(db_session)

    result = await repo.execute_plan(plan)

    assert result.rows[0]["population_sum"] == 100
    assert result.rows[0]["population_avg"] == 100
    assert result.rows[0]["population_min"] == 100
    assert result.rows[0]["population_max"] == 100


@pytest.mark.asyncio
async def test_repository_supports_sorting_and_pagination(db_session):
    job = await _make_dataset(db_session)
    planner = AnalyticsQueryPlanner(
        db_session, metadata_resolver=IngestionMetadataResolver(db_session)
    )
    query = AnalyticsQuery(
        dataset_reference=DatasetReference(ingestion_job_id=job.id),
        dimensions=[Dimension(column_name="region")],
        measures=[Measure(aggregation=AggregationFunction.COUNT, alias="row_count")],
        sorting=[SortClause(target="region", direction=SortDirection.DESCENDING)],
        limit=1,
        offset=0,
    )
    plan = await planner.plan(query)
    repo = AnalyticsRepository(db_session)

    result = await repo.execute_plan(plan)

    assert len(result.rows) == 1
    assert result.rows[0]["region"] == "South"


@pytest.mark.asyncio
async def test_repository_rejects_analytics_query_directly(db_session):
    job = await _make_dataset(db_session)
    query = AnalyticsQuery(
        dataset_reference=DatasetReference(ingestion_job_id=job.id),
        dimensions=[Dimension(column_name="region")],
        measures=[Measure(aggregation=AggregationFunction.COUNT, alias="row_count")],
    )
    repo = AnalyticsRepository(db_session)

    with pytest.raises(TypeError):
        await repo.execute_plan(query)


def test_repository_uses_no_text_sql():
    source = inspect.getsource(AnalyticsRepository)
    assert "text(" not in source


def test_planner_and_repository_have_no_fastapi_dependencies():
    planner_source = inspect.getsource(AnalyticsQueryPlanner)
    repository_source = inspect.getsource(AnalyticsRepository)
    assert "fastapi" not in planner_source.lower()
    assert "fastapi" not in repository_source.lower()
