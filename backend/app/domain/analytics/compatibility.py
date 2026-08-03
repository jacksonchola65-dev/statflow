from __future__ import annotations

from app.domain.analytics.contracts import AggregationFunction
from app.models.ingestion import InferredColumnType

_DIMENSION_ELIGIBLE_TYPES: frozenset[InferredColumnType] = frozenset(
    {
        InferredColumnType.TEXT,
        InferredColumnType.BOOLEAN,
        InferredColumnType.DATE,
        InferredColumnType.DATETIME,
        InferredColumnType.INTEGER,
        InferredColumnType.DECIMAL,
    }
)

_AGGREGATIONS_BY_TYPE: dict[InferredColumnType, tuple[AggregationFunction, ...]] = {
    InferredColumnType.INTEGER: (
        AggregationFunction.COUNT,
        AggregationFunction.COUNT_DISTINCT,
        AggregationFunction.SUM,
        AggregationFunction.AVERAGE,
        AggregationFunction.MINIMUM,
        AggregationFunction.MAXIMUM,
    ),
    InferredColumnType.DECIMAL: (
        AggregationFunction.COUNT,
        AggregationFunction.COUNT_DISTINCT,
        AggregationFunction.SUM,
        AggregationFunction.AVERAGE,
        AggregationFunction.MINIMUM,
        AggregationFunction.MAXIMUM,
    ),
    InferredColumnType.DATE: (
        AggregationFunction.COUNT,
        AggregationFunction.COUNT_DISTINCT,
        AggregationFunction.MINIMUM,
        AggregationFunction.MAXIMUM,
    ),
    InferredColumnType.DATETIME: (
        AggregationFunction.COUNT,
        AggregationFunction.COUNT_DISTINCT,
        AggregationFunction.MINIMUM,
        AggregationFunction.MAXIMUM,
    ),
    InferredColumnType.TEXT: (
        AggregationFunction.COUNT,
        AggregationFunction.COUNT_DISTINCT,
    ),
    InferredColumnType.BOOLEAN: (
        AggregationFunction.COUNT,
        AggregationFunction.COUNT_DISTINCT,
    ),
}


def is_dimension_eligible(inferred_type: InferredColumnType) -> bool:
    return inferred_type in _DIMENSION_ELIGIBLE_TYPES


def supported_aggregations(inferred_type: InferredColumnType) -> tuple[AggregationFunction, ...]:
    return _AGGREGATIONS_BY_TYPE.get(inferred_type, ())


def is_aggregation_supported(
    inferred_type: InferredColumnType, aggregation: AggregationFunction
) -> bool:
    return aggregation in supported_aggregations(inferred_type)
