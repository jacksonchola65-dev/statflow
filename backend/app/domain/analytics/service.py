from __future__ import annotations

import logging
from time import perf_counter

from app.domain.analytics.contracts import AnalyticsQuery, AnalyticsResult
from app.domain.analytics.planner import AnalyticsQueryPlanner
from app.domain.analytics.repository import AnalyticsRepository

logger = logging.getLogger(__name__)


class AnalyticsService:
    """Orchestrate analytics query planning and execution."""

    def __init__(self, planner: AnalyticsQueryPlanner, repository: AnalyticsRepository) -> None:
        self._planner = planner
        self._repository = repository

    async def execute(self, query: AnalyticsQuery) -> AnalyticsResult:
        start = perf_counter()
        result = await self._repository.execute_plan(await self._planner.plan(query))
        duration_ms = round((perf_counter() - start) * 1000, 2)

        logger.info(
            "Analytics query executed",
            extra={
                "ingestion_job_id": str(query.dataset_reference.ingestion_job_id),
                "dimension_count": len(query.dimensions),
                "measure_count": len(query.measures),
                "filter_count": len(query.filters),
                "sort_count": len(query.sorting),
                "limit": query.limit,
                "offset": query.offset,
                "row_count": result.row_count,
                "duration_ms": duration_ms,
            },
        )

        return result
