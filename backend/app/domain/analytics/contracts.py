from __future__ import annotations

import re
import uuid
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any, ClassVar, TypeAlias

from app.models.ingestion import IngestionStatus
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class AnalyticsQueryError(Exception):
    """Base class for analytics-domain validation exceptions."""


class InvalidAnalyticsQueryError(AnalyticsQueryError, ValueError):
    """Raised when an analytics query is invalid."""


class InvalidAnalyticsIdentifierError(AnalyticsQueryError, ValueError):
    """Raised when an analytics identifier is invalid."""


class InvalidMeasureError(AnalyticsQueryError, ValueError):
    """Raised when a measure definition is invalid."""


class InvalidFilterError(AnalyticsQueryError, ValueError):
    """Raised when a filter definition is invalid."""


class InvalidSortError(AnalyticsQueryError, ValueError):
    """Raised when a sort definition is invalid."""


class AggregationFunction(str, Enum):
    COUNT = "COUNT"
    COUNT_DISTINCT = "COUNT_DISTINCT"
    SUM = "SUM"
    AVERAGE = "AVERAGE"
    MINIMUM = "MINIMUM"
    MAXIMUM = "MAXIMUM"


class FilterOperator(str, Enum):
    EQUALS = "EQUALS"
    NOT_EQUALS = "NOT_EQUALS"
    GREATER_THAN = "GREATER_THAN"
    GREATER_THAN_OR_EQUAL = "GREATER_THAN_OR_EQUAL"
    LESS_THAN = "LESS_THAN"
    LESS_THAN_OR_EQUAL = "LESS_THAN_OR_EQUAL"
    IN = "IN"
    NOT_IN = "NOT_IN"
    IS_NULL = "IS_NULL"
    IS_NOT_NULL = "IS_NOT_NULL"


class SortDirection(str, Enum):
    ASCENDING = "ASCENDING"
    DESCENDING = "DESCENDING"


class AnalyticsResultRole(str, Enum):
    DIMENSION = "dimension"
    MEASURE = "measure"


IdentifierName: TypeAlias = str
AnalyticsValue: TypeAlias = str | int | float | bool | Decimal | date | datetime | None | list[Any]


class DatasetReference(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    ingestion_job_id: uuid.UUID
    registry_id: uuid.UUID | None = None
    dataset_version: int | None = None


class Dimension(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    column_name: str = Field(min_length=1)
    alias: str | None = None

    @field_validator("column_name")
    @classmethod
    def validate_identifier(cls, value: str) -> str:
        if not value or not value.strip():
            raise InvalidAnalyticsIdentifierError("column_name must not be empty")
        if value.strip() != value:
            raise InvalidAnalyticsIdentifierError(
                "column_name must not have surrounding whitespace"
            )
        if re.search(r"[\s;\-\n\r\t]|/\*|\*/|--|['\"`]|[<>]", value):
            raise InvalidAnalyticsIdentifierError("column_name contains unsupported characters")
        if value in {"*", "?"}:
            raise InvalidAnalyticsIdentifierError("wildcard identifiers are not supported")
        if any(ord(ch) < 32 for ch in value):
            raise InvalidAnalyticsIdentifierError("control characters are not allowed")
        return value

    @field_validator("alias")
    @classmethod
    def validate_alias(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if not value or not value.strip():
            raise InvalidAnalyticsIdentifierError("alias must not be empty")
        if re.search(r"[\s;\-\n\r\t]|/\*|\*/|--|['\"`]|[<>]", value):
            raise InvalidAnalyticsIdentifierError("alias contains unsupported characters")
        if any(ord(ch) < 32 for ch in value):
            raise InvalidAnalyticsIdentifierError("control characters are not allowed")
        return value


class Measure(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    aggregation: AggregationFunction
    column_name: str | None = None
    alias: str | None = None

    @field_validator("column_name")
    @classmethod
    def validate_column_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if not value or not value.strip():
            raise InvalidMeasureError("column_name must not be empty")
        return value

    @model_validator(mode="after")
    def validate_aggregation_requirements(self) -> "Measure":
        if self.aggregation in {AggregationFunction.COUNT}:
            return self
        if self.aggregation == AggregationFunction.COUNT_DISTINCT:
            if self.column_name is None:
                raise InvalidMeasureError("COUNT_DISTINCT requires a column_name")
            return self
        if self.column_name is None:
            raise InvalidMeasureError("this aggregation requires a column_name")
        return self


class FilterClause(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    column_name: str
    operator: FilterOperator
    value: AnalyticsValue | None = None

    @field_validator("column_name")
    @classmethod
    def validate_column_name(cls, value: str) -> str:
        if not value or not value.strip():
            raise InvalidFilterError("column_name must not be empty")
        return value

    @model_validator(mode="after")
    def validate_operator_requirements(self) -> "FilterClause":
        if self.operator in {FilterOperator.IS_NULL, FilterOperator.IS_NOT_NULL}:
            if self.value is not None:
                raise InvalidFilterError("null checks do not support a value")
            return self

        if self.operator in {FilterOperator.IN, FilterOperator.NOT_IN}:
            if not isinstance(self.value, list) or not self.value:
                raise InvalidFilterError("IN/NOT_IN requires a non-empty list")
            return self

        if self.value is None:
            raise InvalidFilterError("scalar comparison operators require a value")
        return self


class SortClause(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    target: str
    direction: SortDirection = SortDirection.ASCENDING

    @field_validator("target")
    @classmethod
    def validate_target(cls, value: str) -> str:
        if not value or not value.strip():
            raise InvalidSortError("target must not be empty")
        return value


class AnalyticsQuery(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    MAX_DIMENSIONS: ClassVar[int] = 5
    MAX_MEASURES: ClassVar[int] = 10
    MAX_FILTERS: ClassVar[int] = 20
    MAX_SORTS: ClassVar[int] = 5
    DEFAULT_LIMIT: ClassVar[int] = 100
    MAX_LIMIT: ClassVar[int] = 1000

    dataset_reference: DatasetReference
    dimensions: list[Dimension] = Field(default_factory=list)
    measures: list[Measure] = Field(default_factory=list)
    filters: list[FilterClause] = Field(default_factory=list)
    sorting: list[SortClause] = Field(default_factory=list)
    limit: int = Field(default=DEFAULT_LIMIT)
    offset: int = Field(default=0)

    @field_validator("limit")
    @classmethod
    def validate_limit(cls, value: int) -> int:
        if value < 1:
            raise InvalidAnalyticsQueryError("limit must be positive")
        return value

    @field_validator("offset")
    @classmethod
    def validate_offset(cls, value: int) -> int:
        if value < 0:
            raise InvalidAnalyticsQueryError("offset must be non-negative")
        return value

    @model_validator(mode="after")
    def validate_query(self) -> "AnalyticsQuery":
        if not self.dimensions and not self.measures:
            raise InvalidAnalyticsQueryError("query requires at least one dimension or measure")
        if len(self.dimensions) > self.MAX_DIMENSIONS:
            raise InvalidAnalyticsQueryError("too many dimensions")
        if len(self.measures) > self.MAX_MEASURES:
            raise InvalidAnalyticsQueryError("too many measures")
        if len(self.filters) > self.MAX_FILTERS:
            raise InvalidAnalyticsQueryError("too many filters")
        if len(self.sorting) > self.MAX_SORTS:
            raise InvalidAnalyticsQueryError("too many sorts")
        if self.limit > self.MAX_LIMIT:
            raise InvalidAnalyticsQueryError("limit exceeds maximum")
        if self.limit < 1:
            raise InvalidAnalyticsQueryError("limit must be positive")

        dimension_names = [dimension.column_name for dimension in self.dimensions]
        if len(dimension_names) != len(set(dimension_names)):
            raise InvalidAnalyticsQueryError("duplicate dimensions are not allowed")

        aliases = []
        for dimension in self.dimensions:
            if dimension.alias is not None:
                aliases.append(dimension.alias)
        for measure in self.measures:
            if measure.alias is not None:
                aliases.append(measure.alias)

        if len(aliases) != len(set(aliases)):
            raise InvalidAnalyticsQueryError("duplicate aliases are not allowed")

        declared_identifiers = set(dimension_names)
        for dimension in self.dimensions:
            if dimension.alias is not None:
                declared_identifiers.add(dimension.alias)
        for measure in self.measures:
            if measure.alias is not None:
                declared_identifiers.add(measure.alias)

        for dimension in self.dimensions:
            if dimension.alias is not None and dimension.alias in dimension_names:
                raise InvalidAnalyticsQueryError("alias conflicts with dimension identifier")
        for measure in self.measures:
            if measure.alias is not None and measure.alias in dimension_names:
                raise InvalidAnalyticsQueryError("alias conflicts with dimension identifier")

        sort_targets = [sort.target for sort in self.sorting]
        for target in sort_targets:
            if target not in declared_identifiers:
                raise InvalidSortError("sort target must reference a declared identifier")
        if len(sort_targets) != len(set(sort_targets)):
            raise InvalidSortError("duplicate sort targets are not allowed")

        return self


class AnalyticsResultColumn(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    identifier: str
    label: str
    role: AnalyticsResultRole
    aggregation: AggregationFunction | None = None
    data_type: str | None = None

    @field_validator("identifier")
    @classmethod
    def validate_identifier(cls, value: str) -> str:
        if not value or not value.strip():
            raise InvalidAnalyticsIdentifierError("identifier must not be empty")
        return value


class AnalyticsResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    ingestion_job_id: uuid.UUID
    columns: list[AnalyticsResultColumn]
    rows: list[dict[str, AnalyticsValue]]
    row_count: int
    limit: int
    offset: int
    has_more: bool

    @field_validator("row_count")
    @classmethod
    def validate_row_count(cls, value: int) -> int:
        if value < 0:
            raise InvalidAnalyticsQueryError("row_count must be non-negative")
        return value

    @model_validator(mode="after")
    def validate_rows(self) -> "AnalyticsResult":
        expected_keys = {column.identifier for column in self.columns}
        for row in self.rows:
            missing = expected_keys.difference(row.keys())
            if missing:
                raise InvalidAnalyticsQueryError("row is missing required result keys")
            extra = set(row.keys()).difference(expected_keys)
            if extra:
                raise InvalidAnalyticsQueryError("row contains unknown result keys")
        return self


class DatasetSummary(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    ingestion_job_id: uuid.UUID
    source_name: str | None = None
    dataset_name: str
    status: IngestionStatus
    row_count: int
    column_count: int
    completed_at: datetime | None = None
    created_at: datetime
    description: str | None = None


class DatasetListResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    items: list[DatasetSummary]
    total: int
    limit: int
    offset: int
    has_more: bool


class DatasetColumnDescriptor(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    identifier: str
    display_name: str
    inferred_type: str
    nullable: bool
    ordinal_position: int
    semantic_role: str | None = None
    dimension_eligible: bool
    measure_eligible: bool
    supported_aggregations: list[AggregationFunction]


class AnalyticsDimensionDescriptor(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    identifier: str
    display_name: str
    data_type: str


class AnalyticsMeasureDescriptor(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    identifier: str
    display_name: str
    data_type: str
    supported_aggregations: list[AggregationFunction]


class DatasetDetails(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    summary: DatasetSummary
    columns: list[DatasetColumnDescriptor]
    available_dimensions: list[AnalyticsDimensionDescriptor]
    available_measures: list[AnalyticsMeasureDescriptor]
    preview_available: bool
    analytics_ready: bool


class DatasetPreviewResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    ingestion_job_id: uuid.UUID
    columns: list[str]
    rows: list[dict[str, AnalyticsValue]]
    limit: int
    returned_count: int


class DatasetStatistics(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    ingestion_job_id: uuid.UUID
    row_count: int
    column_count: int
    nullable_column_count: int
    numeric_column_count: int
    text_column_count: int
    date_column_count: int
    datetime_column_count: int
    boolean_column_count: int
    completed_at: datetime | None = None
