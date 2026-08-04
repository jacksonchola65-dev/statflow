from __future__ import annotations

from typing import Any

from app.domain.analytics.contracts import (
    AggregationFunction,
    AnalyticsResult,
    AnalyticsResultColumn,
    AnalyticsResultRole,
)
from app.domain.analytics.exceptions import (
    InvalidAggregationError,
    InvalidExecutionPlanError,
    InvalidIdentifierError,
)
from app.domain.analytics.planner import (
    AnalyticsExecutionPlan,
    ResolvedFilter,
    ResolvedMeasure,
)
from app.models.ingestion import DatasetColumn, DatasetRow, InferredColumnType
from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Integer,
    Numeric,
    bindparam,
    cast,
    func,
    select,
)
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql.elements import BindParameter


class AnalyticsRepository:
    """Execute validated analytics execution plans against persisted ingestion data."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def execute_plan(self, plan: AnalyticsExecutionPlan) -> AnalyticsResult:
        if not isinstance(plan, AnalyticsExecutionPlan):
            raise TypeError("AnalyticsRepository.execute_plan() expects an AnalyticsExecutionPlan")

        if not plan.resolved_dimensions and not plan.resolved_measures:
            raise InvalidExecutionPlanError("execution plan must include dimensions or measures")

        selected_columns: list[Any] = []
        output_identifiers: list[str] = []
        output_roles: list[AnalyticsResultRole] = []
        output_aggregations: list[AggregationFunction | None] = []
        output_labels: list[str] = []

        for resolved_dimension in plan.resolved_dimensions:
            identifier = (
                resolved_dimension.dimension.alias or resolved_dimension.dimension.column_name
            )
            expression = self._build_column_expression(resolved_dimension.metadata)
            selected_columns.append(expression.label(identifier))
            output_identifiers.append(identifier)
            output_roles.append(AnalyticsResultRole.DIMENSION)
            output_aggregations.append(None)
            output_labels.append(identifier)

        for resolved_measure in plan.resolved_measures:
            identifier = (
                resolved_measure.measure.alias or resolved_measure.measure.aggregation.value.lower()
            )
            expression = self._build_measure_expression(resolved_measure)
            selected_columns.append(expression.label(identifier))
            output_identifiers.append(identifier)
            output_roles.append(AnalyticsResultRole.MEASURE)
            output_aggregations.append(resolved_measure.measure.aggregation)
            output_labels.append(identifier)

        query = (
            select(*selected_columns)
            .select_from(DatasetRow)
            .where(DatasetRow.ingestion_job_id == plan.ingestion_job_id)
        )

        if plan.resolved_filters:
            query = query.where(
                *[
                    self._build_filter_expression(filter_clause)
                    for filter_clause in plan.resolved_filters
                ]
            )

        if plan.resolved_dimensions:
            grouping_expressions = [
                self._build_column_expression(dimension.metadata)
                for dimension in plan.resolved_dimensions
            ]
            query = query.group_by(*grouping_expressions)

        for resolved_sort in plan.resolved_sorts:
            expression = next(
                (
                    column
                    for column in selected_columns
                    if getattr(column, "name", None) == resolved_sort.identifier
                ),
                None,
            )
            if expression is None:
                raise InvalidIdentifierError(f"unknown sort target: {resolved_sort.identifier}")
            query = query.order_by(
                expression.asc()
                if resolved_sort.sort_clause.direction.value == "ASCENDING"
                else expression.desc()
            )

        query = query.limit(plan.limit).offset(plan.offset)

        result = await self._session.execute(query)
        rows = result.all()
        output_rows: list[dict[str, Any]] = []
        for row in rows:
            mapping = {}
            for identifier, value in zip(output_identifiers, row):
                mapping[identifier] = value
            output_rows.append(mapping)

        columns = [
            AnalyticsResultColumn(
                identifier=identifier, label=label, role=role, aggregation=aggregation
            )
            for identifier, label, role, aggregation in zip(
                output_identifiers, output_labels, output_roles, output_aggregations
            )
        ]

        return AnalyticsResult(
            ingestion_job_id=plan.ingestion_job_id,
            columns=columns,
            rows=output_rows,
            row_count=len(output_rows),
            limit=plan.limit,
            offset=plan.offset,
            has_more=False,
        )

    def _build_measure_expression(self, resolved_measure: ResolvedMeasure) -> Any:
        measure = resolved_measure.measure
        metadata = resolved_measure.metadata
        if metadata is None:
            if measure.aggregation != AggregationFunction.COUNT:
                raise InvalidAggregationError("this aggregation requires a column")
            return func.count()

        column_expression = self._build_column_expression(metadata)
        if measure.aggregation == AggregationFunction.COUNT:
            return func.count(column_expression)
        if measure.aggregation == AggregationFunction.COUNT_DISTINCT:
            return func.count(func.distinct(column_expression))
        if measure.aggregation == AggregationFunction.SUM:
            return func.sum(column_expression)
        if measure.aggregation == AggregationFunction.AVERAGE:
            return func.avg(column_expression)
        if measure.aggregation == AggregationFunction.MINIMUM:
            return func.min(column_expression)
        if measure.aggregation == AggregationFunction.MAXIMUM:
            return func.max(column_expression)
        raise InvalidAggregationError("unsupported aggregation")

    def _build_filter_expression(self, resolved_filter: ResolvedFilter) -> Any:
        column_expression = self._build_column_expression(resolved_filter.metadata)
        operator = resolved_filter.filter_clause.operator
        if operator == "EQUALS":
            return column_expression == resolved_filter.filter_clause.value
        if operator == "NOT_EQUALS":
            return column_expression != resolved_filter.filter_clause.value
        if operator == "GREATER_THAN":
            return column_expression > resolved_filter.filter_clause.value
        if operator == "GREATER_THAN_OR_EQUAL":
            return column_expression >= resolved_filter.filter_clause.value
        if operator == "LESS_THAN":
            return column_expression < resolved_filter.filter_clause.value
        if operator == "LESS_THAN_OR_EQUAL":
            return column_expression <= resolved_filter.filter_clause.value
        if operator == "IN":
            return column_expression.in_(resolved_filter.filter_clause.value)
        if operator == "NOT_IN":
            return column_expression.notin_(resolved_filter.filter_clause.value)
        if operator == "IS_NULL":
            return column_expression.is_(None)
        if operator == "IS_NOT_NULL":
            return column_expression.is_not(None)
        raise InvalidAggregationError("unsupported filter operator")

    def _build_column_expression(self, metadata: DatasetColumn) -> Any:
        json_key: BindParameter[Any] = bindparam(
            f"analytics_key_{metadata.normalized_name}",
            value=metadata.normalized_name,
            literal_execute=True,
        )
        json_value = DatasetRow.values[json_key].astext
        inferred_type = metadata.inferred_type
        if inferred_type == InferredColumnType.INTEGER:
            return cast(json_value, Integer)
        if inferred_type == InferredColumnType.DECIMAL:
            return cast(json_value, Numeric)
        if inferred_type == InferredColumnType.BOOLEAN:
            return cast(json_value, Boolean)
        if inferred_type == InferredColumnType.DATE:
            return cast(json_value, Date)
        if inferred_type == InferredColumnType.DATETIME:
            return cast(json_value, DateTime)
        return json_value
