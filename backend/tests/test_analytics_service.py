from __future__ import annotations

import asyncio
import inspect
import uuid

import pytest

from app.domain.analytics.contracts import (
    AggregationFunction,
    AnalyticsQuery,
    AnalyticsResult,
    AnalyticsResultColumn,
    AnalyticsResultRole,
    DatasetReference,
    Dimension,
    Measure,
)
from app.domain.analytics.planner import AnalyticsExecutionPlan
from app.domain.analytics.service import AnalyticsService


class DummyPlanner:
    def __init__(self, plan: AnalyticsExecutionPlan | None = None) -> None:
        self.planned = False
        self.query = None
        self._plan = plan

    async def plan(self, query: AnalyticsQuery) -> AnalyticsExecutionPlan:
        self.planned = True
        self.query = query
        if self._plan is None:
            raise RuntimeError("no plan configured")
        return self._plan


class DummyRepository:
    def __init__(self) -> None:
        self.executed = False
        self.plan = None

    async def execute_plan(self, plan: AnalyticsExecutionPlan) -> AnalyticsResult:
        self.executed = True
        self.plan = plan
        return self._result


async def _build_query() -> AnalyticsQuery:
    return AnalyticsQuery(
        dataset_reference=DatasetReference(ingestion_job_id=uuid.uuid4()),
        dimensions=[Dimension(column_name="region")],
        measures=[Measure(aggregation=AggregationFunction.COUNT, alias="row_count")],
    )


async def _build_result(ingestion_job_id: uuid.UUID) -> AnalyticsResult:
    return AnalyticsResult(
        ingestion_job_id=ingestion_job_id,
        columns=[
            AnalyticsResultColumn(
                identifier="region",
                label="region",
                role=AnalyticsResultRole.DIMENSION,
                aggregation=None,
            ),
            AnalyticsResultColumn(
                identifier="row_count",
                label="row_count",
                role=AnalyticsResultRole.MEASURE,
                aggregation=AggregationFunction.COUNT,
            ),
        ],
        rows=[{"region": "North", "row_count": 1}],
        row_count=1,
        limit=100,
        offset=0,
        has_more=False,
    )


async def test_execute_invokes_planner_and_repository() -> None:
    query = await _build_query()
    plan = AnalyticsExecutionPlan(
        ingestion_job_id=query.dataset_reference.ingestion_job_id,
        dataset_table="dataset_rows",
        resolved_dimensions=(),
        resolved_measures=(),
        resolved_filters=(),
        resolved_sorts=(),
        limit=query.limit,
        offset=query.offset,
    )
    planner = DummyPlanner(plan=plan)
    repository = DummyRepository()
    repository._result = await _build_result(query.dataset_reference.ingestion_job_id)

    service = AnalyticsService(planner, repository)
    result = await service.execute(query)

    assert planner.planned is True
    assert planner.query == query
    assert repository.executed is True
    assert repository.plan == plan
    assert result == repository._result


async def test_service_propagates_planner_error() -> None:
    query = await _build_query()

    class BrokenPlanner(DummyPlanner):
        async def plan(self, query: AnalyticsQuery) -> AnalyticsExecutionPlan:
            raise RuntimeError("planner failure")

    service = AnalyticsService(BrokenPlanner(), DummyRepository())

    with pytest.raises(RuntimeError, match="planner failure"):
        await service.execute(query)


async def test_service_propagates_repository_error() -> None:
    query = await _build_query()

    class BrokenRepository(DummyRepository):
        async def execute_plan(self, plan: AnalyticsExecutionPlan) -> AnalyticsResult:
            raise RuntimeError("repository failure")

    plan = AnalyticsExecutionPlan(
        ingestion_job_id=query.dataset_reference.ingestion_job_id,
        dataset_table="dataset_rows",
        resolved_dimensions=(),
        resolved_measures=(),
        resolved_filters=(),
        resolved_sorts=(),
        limit=query.limit,
        offset=query.offset,
    )
    service = AnalyticsService(DummyPlanner(plan=plan), BrokenRepository())

    with pytest.raises(RuntimeError, match="repository failure"):
        await service.execute(query)


async def test_service_propagates_cancellation() -> None:
    query = await _build_query()

    class CancelledPlanner(DummyPlanner):
        async def plan(self, query: AnalyticsQuery) -> AnalyticsExecutionPlan:
            raise asyncio.CancelledError()

    service = AnalyticsService(CancelledPlanner(), DummyRepository())

    with pytest.raises(asyncio.CancelledError):
        await service.execute(query)


def test_service_does_not_import_fastapi_or_sqlalchemy() -> None:
    source = inspect.getsource(AnalyticsService)
    assert "fastapi" not in source
    assert "sqlalchemy" not in source
