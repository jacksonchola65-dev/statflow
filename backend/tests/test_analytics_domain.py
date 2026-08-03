from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import uuid4

import pytest
from app.domain.analytics import (
    AggregationFunction,
    AnalyticsQuery,
    AnalyticsResult,
    AnalyticsResultColumn,
    DatasetReference,
    Dimension,
    FilterClause,
    FilterOperator,
    Measure,
    SortClause,
    SortDirection,
)
from pydantic import ValidationError


def test_count_without_column_is_valid() -> None:
    measure = Measure(aggregation=AggregationFunction.COUNT)
    assert measure.aggregation is AggregationFunction.COUNT
    assert measure.column_name is None


def test_count_with_column_is_valid() -> None:
    measure = Measure(aggregation=AggregationFunction.COUNT, column_name="population")
    assert measure.column_name == "population"


def test_count_distinct_without_column_rejected() -> None:
    with pytest.raises(ValidationError):
        Measure(aggregation=AggregationFunction.COUNT_DISTINCT)


@pytest.mark.parametrize(
    "aggregation",
    [
        AggregationFunction.SUM,
        AggregationFunction.AVERAGE,
        AggregationFunction.MINIMUM,
        AggregationFunction.MAXIMUM,
    ],
)
def test_other_aggregations_require_column(aggregation: AggregationFunction) -> None:
    with pytest.raises(ValidationError):
        Measure(aggregation=aggregation)


@pytest.mark.parametrize(
    "value",
    ["population_count", "region_code", "year_2024"],
)
def test_valid_normalized_identifier_accepted(value: str) -> None:
    dimension = Dimension(column_name=value)
    assert dimension.column_name == value


@pytest.mark.parametrize(
    "value",
    ["", "   ", "population; drop table", "*", "-- comment", "name\nwith-break", "bad\tname"],
)
def test_invalid_identifier_rejected(value: str) -> None:
    with pytest.raises(ValidationError):
        Dimension(column_name=value)


def test_duplicate_dimensions_rejected() -> None:
    with pytest.raises(ValidationError):
        AnalyticsQuery(
            dataset_reference=DatasetReference(ingestion_job_id=uuid4()),
            dimensions=[Dimension(column_name="region"), Dimension(column_name="region")],
            measures=[Measure(aggregation=AggregationFunction.COUNT)],
        )


def test_scalar_filter_with_value_accepted() -> None:
    clause = FilterClause(column_name="population", operator=FilterOperator.GREATER_THAN, value=100)
    assert clause.value == 100


def test_scalar_filter_without_value_rejected() -> None:
    with pytest.raises(ValidationError):
        FilterClause(column_name="population", operator=FilterOperator.GREATER_THAN)


def test_in_filter_with_non_empty_list_accepted() -> None:
    clause = FilterClause(
        column_name="region", operator=FilterOperator.IN, value=["north", "south"]
    )
    assert clause.value == ["north", "south"]


def test_in_filter_with_empty_list_rejected() -> None:
    with pytest.raises(ValidationError):
        FilterClause(column_name="region", operator=FilterOperator.IN, value=[])


def test_in_filter_with_scalar_rejected() -> None:
    with pytest.raises(ValidationError):
        FilterClause(column_name="region", operator=FilterOperator.IN, value="north")


def test_is_null_without_value_accepted() -> None:
    clause = FilterClause(column_name="population", operator=FilterOperator.IS_NULL)
    assert clause.value is None


def test_is_null_with_value_rejected() -> None:
    with pytest.raises(ValidationError):
        FilterClause(column_name="population", operator=FilterOperator.IS_NULL, value=1)


def test_is_not_null_without_value_accepted() -> None:
    clause = FilterClause(column_name="population", operator=FilterOperator.IS_NOT_NULL)
    assert clause.value is None


def test_declared_dimension_sort_accepted() -> None:
    query = AnalyticsQuery(
        dataset_reference=DatasetReference(ingestion_job_id=uuid4()),
        dimensions=[Dimension(column_name="region")],
        measures=[Measure(aggregation=AggregationFunction.COUNT, alias="row_count")],
        sorting=[SortClause(target="region", direction=SortDirection.ASCENDING)],
    )
    assert query.sorting[0].target == "region"


def test_declared_measure_alias_sort_accepted() -> None:
    query = AnalyticsQuery(
        dataset_reference=DatasetReference(ingestion_job_id=uuid4()),
        dimensions=[Dimension(column_name="region")],
        measures=[Measure(aggregation=AggregationFunction.COUNT, alias="row_count")],
        sorting=[SortClause(target="row_count", direction=SortDirection.DESCENDING)],
    )
    assert query.sorting[0].target == "row_count"


def test_undeclared_sort_target_rejected() -> None:
    with pytest.raises(ValidationError):
        AnalyticsQuery(
            dataset_reference=DatasetReference(ingestion_job_id=uuid4()),
            dimensions=[Dimension(column_name="region")],
            measures=[Measure(aggregation=AggregationFunction.COUNT, alias="row_count")],
            sorting=[SortClause(target="missing_target", direction=SortDirection.ASCENDING)],
        )


def test_duplicate_sort_target_rejected() -> None:
    with pytest.raises(ValidationError):
        AnalyticsQuery(
            dataset_reference=DatasetReference(ingestion_job_id=uuid4()),
            dimensions=[Dimension(column_name="region")],
            measures=[Measure(aggregation=AggregationFunction.COUNT, alias="row_count")],
            sorting=[
                SortClause(target="region", direction=SortDirection.ASCENDING),
                SortClause(target="region", direction=SortDirection.DESCENDING),
            ],
        )


def test_dimension_maximum_enforced() -> None:
    with pytest.raises(ValidationError):
        AnalyticsQuery(
            dataset_reference=DatasetReference(ingestion_job_id=uuid4()),
            dimensions=[Dimension(column_name=f"dim_{index}") for index in range(6)],
            measures=[Measure(aggregation=AggregationFunction.COUNT)],
        )


def test_measure_maximum_enforced() -> None:
    with pytest.raises(ValidationError):
        AnalyticsQuery(
            dataset_reference=DatasetReference(ingestion_job_id=uuid4()),
            dimensions=[Dimension(column_name="region")],
            measures=[
                Measure(aggregation=AggregationFunction.SUM, column_name="population")
                for _ in range(11)
            ],
        )


def test_filter_maximum_enforced() -> None:
    with pytest.raises(ValidationError):
        AnalyticsQuery(
            dataset_reference=DatasetReference(ingestion_job_id=uuid4()),
            dimensions=[Dimension(column_name="region")],
            measures=[Measure(aggregation=AggregationFunction.COUNT)],
            filters=[
                FilterClause(column_name="region", operator=FilterOperator.EQUALS, value="north")
                for _ in range(21)
            ],
        )


def test_sort_maximum_enforced() -> None:
    with pytest.raises(ValidationError):
        AnalyticsQuery(
            dataset_reference=DatasetReference(ingestion_job_id=uuid4()),
            dimensions=[Dimension(column_name="region")],
            measures=[Measure(aggregation=AggregationFunction.COUNT)],
            sorting=[
                SortClause(target="region", direction=SortDirection.ASCENDING) for _ in range(6)
            ],
        )


def test_default_limit_and_negative_offset() -> None:
    query = AnalyticsQuery(
        dataset_reference=DatasetReference(ingestion_job_id=uuid4()),
        dimensions=[Dimension(column_name="region")],
        measures=[Measure(aggregation=AggregationFunction.COUNT)],
    )
    assert query.limit == 100
    assert query.offset == 0

    with pytest.raises(ValidationError):
        AnalyticsQuery(
            dataset_reference=DatasetReference(ingestion_job_id=uuid4()),
            dimensions=[Dimension(column_name="region")],
            measures=[Measure(aggregation=AggregationFunction.COUNT)],
            offset=-1,
        )


def test_query_with_no_dimensions_or_measures_rejected() -> None:
    with pytest.raises(ValidationError):
        AnalyticsQuery(dataset_reference=DatasetReference(ingestion_job_id=uuid4()))


def test_duplicate_aliases_rejected() -> None:
    with pytest.raises(ValidationError):
        AnalyticsQuery(
            dataset_reference=DatasetReference(ingestion_job_id=uuid4()),
            dimensions=[Dimension(column_name="region", alias="group_by")],
            measures=[Measure(aggregation=AggregationFunction.COUNT, alias="group_by")],
        )


def test_alias_conflicting_with_dimension_identifier_rejected() -> None:
    with pytest.raises(ValidationError):
        AnalyticsQuery(
            dataset_reference=DatasetReference(ingestion_job_id=uuid4()),
            dimensions=[Dimension(column_name="region")],
            measures=[Measure(aggregation=AggregationFunction.COUNT, alias="region")],
        )


def test_ambiguous_output_identifiers_rejected() -> None:
    with pytest.raises(ValidationError):
        AnalyticsQuery(
            dataset_reference=DatasetReference(ingestion_job_id=uuid4()),
            dimensions=[Dimension(column_name="region", alias="shared")],
            measures=[Measure(aggregation=AggregationFunction.COUNT, alias="shared")],
        )


def test_result_with_mapping_rows_validates() -> None:
    result = AnalyticsResult(
        ingestion_job_id=uuid4(),
        columns=[
            AnalyticsResultColumn(identifier="region", label="region", role="dimension"),
            AnalyticsResultColumn(
                identifier="row_count",
                label="row_count",
                role="measure",
                aggregation=AggregationFunction.COUNT,
            ),
        ],
        rows=[{"region": "north", "row_count": 3}],
        row_count=1,
        limit=100,
        offset=0,
        has_more=False,
    )
    assert result.rows[0]["region"] == "north"


def test_result_missing_key_rejected() -> None:
    with pytest.raises(ValidationError):
        AnalyticsResult(
            ingestion_job_id=uuid4(),
            columns=[
                AnalyticsResultColumn(identifier="region", label="region", role="dimension"),
                AnalyticsResultColumn(
                    identifier="row_count",
                    label="row_count",
                    role="measure",
                    aggregation=AggregationFunction.COUNT,
                ),
            ],
            rows=[{"region": "north"}],
            row_count=1,
            limit=100,
            offset=0,
            has_more=False,
        )


def test_result_unknown_key_rejected() -> None:
    with pytest.raises(ValidationError):
        AnalyticsResult(
            ingestion_job_id=uuid4(),
            columns=[
                AnalyticsResultColumn(identifier="region", label="region", role="dimension"),
            ],
            rows=[{"row_count": 3}],
            row_count=1,
            limit=100,
            offset=0,
            has_more=False,
        )


def test_row_count_and_has_more_validation() -> None:
    with pytest.raises(ValidationError):
        AnalyticsResult(
            ingestion_job_id=uuid4(),
            columns=[AnalyticsResultColumn(identifier="region", label="region", role="dimension")],
            rows=[{"region": "north"}],
            row_count=-1,
            limit=100,
            offset=0,
            has_more=False,
        )


def test_uuid_enum_and_decimal_serialization() -> None:
    query = AnalyticsQuery(
        dataset_reference=DatasetReference(ingestion_job_id=uuid4()),
        dimensions=[Dimension(column_name="region")],
        measures=[
            Measure(
                aggregation=AggregationFunction.SUM,
                column_name="population",
                alias="population_sum",
            )
        ],
    )
    payload = query.model_dump(mode="json")
    assert isinstance(payload["dataset_reference"]["ingestion_job_id"], str)
    assert payload["measures"][0]["aggregation"] == "SUM"

    result = AnalyticsResult(
        ingestion_job_id=uuid4(),
        columns=[
            AnalyticsResultColumn(
                identifier="population_sum",
                label="population_sum",
                role="measure",
                aggregation=AggregationFunction.SUM,
            )
        ],
        rows=[{"population_sum": Decimal("100.50")}],
        row_count=1,
        limit=100,
        offset=0,
        has_more=False,
    )
    serialized = result.model_dump(mode="json")
    assert serialized["rows"][0]["population_sum"] == "100.50"


def test_date_and_datetime_serialization() -> None:
    result = AnalyticsResult(
        ingestion_job_id=uuid4(),
        columns=[
            AnalyticsResultColumn(identifier="report_date", label="report_date", role="dimension"),
            AnalyticsResultColumn(identifier="event_at", label="event_at", role="dimension"),
        ],
        rows=[
            {
                "report_date": date(2024, 1, 1),
                "event_at": datetime(2024, 1, 1, 12, 0, tzinfo=timezone.utc),
            }
        ],
        row_count=1,
        limit=100,
        offset=0,
        has_more=False,
    )
    payload = result.model_dump(mode="json")
    assert payload["rows"][0]["report_date"] == "2024-01-01"
    assert payload["rows"][0]["event_at"].endswith("Z")
