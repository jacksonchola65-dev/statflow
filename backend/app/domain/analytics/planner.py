from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.domain.analytics.compatibility import (
    is_aggregation_supported,
    is_dimension_eligible,
)
from app.domain.analytics.contracts import (
    AggregationFunction,
    AnalyticsQuery,
    Dimension,
    FilterClause,
    Measure,
    SortClause,
)
from app.domain.analytics.exceptions import (
    AnalyticsQueryError,
    InvalidAggregationError,
    InvalidIdentifierError,
    InvalidSortError,
)
from app.domain.analytics.metadata import IngestionMetadataResolver
from app.models.ingestion import DatasetColumn
from sqlalchemy.ext.asyncio import AsyncSession


@dataclass(frozen=True)
class ResolvedDimension:
    dimension: Dimension
    metadata: DatasetColumn


@dataclass(frozen=True)
class ResolvedMeasure:
    measure: Measure
    metadata: DatasetColumn


@dataclass(frozen=True)
class ResolvedFilter:
    filter_clause: FilterClause
    metadata: DatasetColumn


@dataclass(frozen=True)
class ResolvedSort:
    sort_clause: SortClause
    identifier: str


@dataclass(frozen=True)
class AnalyticsExecutionPlan:
    ingestion_job_id: Any
    dataset_table: str
    resolved_dimensions: tuple[ResolvedDimension, ...]
    resolved_measures: tuple[ResolvedMeasure, ...]
    resolved_filters: tuple[ResolvedFilter, ...]
    resolved_sorts: tuple[ResolvedSort, ...]
    limit: int
    offset: int


class AnalyticsQueryPlanner:
    """Plan validated analytics queries against persisted ingestion metadata."""

    def __init__(
        self, session: AsyncSession, metadata_resolver: IngestionMetadataResolver | None = None
    ) -> None:
        self._session = session
        self._metadata_resolver = metadata_resolver or IngestionMetadataResolver(session)

    async def plan(self, query: AnalyticsQuery) -> AnalyticsExecutionPlan:
        if not isinstance(query, AnalyticsQuery):
            raise TypeError("AnalyticsQueryPlanner.plan() expects an AnalyticsQuery")

        await self._metadata_resolver.resolve_dataset(query.dataset_reference.ingestion_job_id)

        resolved_dimensions: list[ResolvedDimension] = []
        for dimension in query.dimensions:
            resolved = await self._resolve_dimension(
                query.dataset_reference.ingestion_job_id, dimension
            )
            resolved_dimensions.append(resolved)

        resolved_measures: list[ResolvedMeasure] = []
        for measure in query.measures:
            resolved = await self._resolve_measure(
                query.dataset_reference.ingestion_job_id, measure
            )
            resolved_measures.append(resolved)

        resolved_filters: list[ResolvedFilter] = []
        for filter_clause in query.filters:
            resolved = await self._resolve_filter(
                query.dataset_reference.ingestion_job_id, filter_clause
            )
            resolved_filters.append(resolved)

        declared_identifiers = {dimension.column_name for dimension in query.dimensions}
        for dimension in query.dimensions:
            if dimension.alias is not None:
                declared_identifiers.add(dimension.alias)
        for measure in query.measures:
            if measure.alias is not None:
                declared_identifiers.add(measure.alias)

        resolved_sorts: list[ResolvedSort] = []
        for sort_clause in query.sorting:
            if sort_clause.target not in declared_identifiers:
                raise InvalidSortError("sort target must reference a declared identifier")
            resolved_sorts.append(
                ResolvedSort(sort_clause=sort_clause, identifier=sort_clause.target)
            )

        if len(resolved_dimensions) != len(
            {dimension.dimension.column_name for dimension in resolved_dimensions}
        ):
            raise AnalyticsQueryError("duplicate dimensions are not allowed")
        if len(
            {
                measure.measure.alias
                for measure in resolved_measures
                if measure.measure.alias is not None
            }
        ) != len(
            [
                measure.measure.alias
                for measure in resolved_measures
                if measure.measure.alias is not None
            ]
        ):
            raise AnalyticsQueryError("duplicate aliases are not allowed")

        return AnalyticsExecutionPlan(
            ingestion_job_id=query.dataset_reference.ingestion_job_id,
            dataset_table="dataset_rows",
            resolved_dimensions=tuple(resolved_dimensions),
            resolved_measures=tuple(resolved_measures),
            resolved_filters=tuple(resolved_filters),
            resolved_sorts=tuple(resolved_sorts),
            limit=query.limit,
            offset=query.offset,
        )

    async def _resolve_dimension(self, ingestion_job_id, dimension: Dimension) -> ResolvedDimension:
        resolved = await self._metadata_resolver.resolve_column(
            ingestion_job_id, dimension.column_name
        )
        if not is_dimension_eligible(resolved.metadata.inferred_type):
            raise InvalidIdentifierError(
                f"column cannot be used as a dimension: {dimension.column_name}"
            )
        return ResolvedDimension(dimension=dimension, metadata=resolved.metadata)

    async def _resolve_measure(self, ingestion_job_id, measure: Measure) -> ResolvedMeasure:
        resolved = (
            await self._metadata_resolver.resolve_column(ingestion_job_id, measure.column_name)
            if measure.column_name
            else None
        )
        if measure.aggregation in {AggregationFunction.COUNT}:
            if measure.column_name is None:
                return ResolvedMeasure(measure=measure, metadata=None)  # type: ignore[arg-type]
            if resolved is not None and not is_aggregation_supported(
                resolved.metadata.inferred_type, measure.aggregation
            ):
                raise InvalidAggregationError(
                    f"aggregation {measure.aggregation.value} is not supported for column {measure.column_name}"
                )
            return ResolvedMeasure(measure=measure, metadata=resolved.metadata)  # type: ignore[arg-type]
        if measure.aggregation == AggregationFunction.COUNT_DISTINCT:
            if resolved is None:
                raise InvalidIdentifierError("COUNT_DISTINCT requires a column")
            if not is_aggregation_supported(resolved.metadata.inferred_type, measure.aggregation):
                raise InvalidAggregationError(
                    f"aggregation {measure.aggregation.value} is not supported for column {measure.column_name}"
                )
            return ResolvedMeasure(measure=measure, metadata=resolved.metadata)
        if resolved is None:
            raise InvalidIdentifierError("this aggregation requires a column")
        if not is_aggregation_supported(resolved.metadata.inferred_type, measure.aggregation):
            raise InvalidAggregationError(
                f"aggregation {measure.aggregation.value} is not supported for column {measure.column_name}"
            )
        return ResolvedMeasure(measure=measure, metadata=resolved.metadata)

    async def _resolve_filter(
        self, ingestion_job_id, filter_clause: FilterClause
    ) -> ResolvedFilter:
        resolved = await self._metadata_resolver.resolve_column(
            ingestion_job_id, filter_clause.column_name
        )
        return ResolvedFilter(filter_clause=filter_clause, metadata=resolved.metadata)
