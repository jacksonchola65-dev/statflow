"""Provider-neutral contracts for StatFlow's internal tool layer."""

from __future__ import annotations

import uuid
from enum import Enum
from typing import Any

from app.domain.analytics.contracts import AggregationFunction, FilterOperator
from app.models.user import UserRole
from pydantic import BaseModel, ConfigDict, Field, field_validator


class ToolAuthority(str, Enum):
    DETERMINISTIC = "DETERMINISTIC"
    EVIDENCE_GOVERNED = "EVIDENCE_GOVERNED"
    DECISION_GOVERNED = "DECISION_GOVERNED"
    EXPLORATORY = "EXPLORATORY"
    PREVIEW = "PREVIEW"
    SAMPLED = "SAMPLED"


class ToolStatus(str, Enum):
    SUCCESS = "SUCCESS"
    INVALID_ARGUMENTS = "INVALID_ARGUMENTS"
    UNAUTHORIZED = "UNAUTHORIZED"
    FORBIDDEN = "FORBIDDEN"
    NOT_FOUND = "NOT_FOUND"
    UNSUPPORTED_OPERATION = "UNSUPPORTED_OPERATION"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    RESULT_LIMIT_EXCEEDED = "RESULT_LIMIT_EXCEEDED"
    EXECUTION_FAILED = "EXECUTION_FAILED"


class ToolExecutionContext(BaseModel):
    """Trusted server-side context; model arguments cannot populate identity."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    user_id: uuid.UUID
    role: UserRole
    request_id: str = Field(min_length=1, max_length=128)
    workspace_id: uuid.UUID | None = None
    organization_id: uuid.UUID | None = None
    execution_mode: str = Field(default="PRODUCTION", min_length=1, max_length=32)
    audit_metadata: dict[str, str] = Field(default_factory=dict)


class ToolResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tool_name: str
    tool_version: int
    status: ToolStatus
    data: Any = None
    warnings: list[str] = Field(default_factory=list)
    provenance: dict[str, Any] = Field(default_factory=dict)
    authority: ToolAuthority
    execution_metadata: dict[str, Any] = Field(default_factory=dict)
    error_code: str | None = None


class DatasetToolArguments(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    dataset_id: uuid.UUID


class FilterToolArgument(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    column: str = Field(min_length=1, max_length=255)
    operator: FilterOperator
    value: Any = None

    @field_validator("column")
    @classmethod
    def validate_column(cls, value: str) -> str:
        from app.domain.analytics.contracts import Dimension

        Dimension(column_name=value)
        return value


class RunDatasetAnalysisArguments(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    dataset_id: uuid.UUID
    aggregation: AggregationFunction = AggregationFunction.COUNT
    measure: str | None = Field(default=None, min_length=1, max_length=255)
    dimension: str | None = Field(default=None, min_length=1, max_length=255)
    filters: list[FilterToolArgument] = Field(default_factory=list, max_length=20)
    limit: int = Field(default=100, ge=1, le=1000)
    offset: int = Field(default=0, ge=0)

    @field_validator("measure", "dimension")
    @classmethod
    def validate_identifier(cls, value: str | None) -> str | None:
        if value is None:
            return None
        from app.domain.analytics.contracts import Dimension

        Dimension(column_name=value)
        return value

    @field_validator("measure")
    @classmethod
    def validate_measure_for_count_distinct(cls, value: str | None) -> str | None:
        return value


class ExplainProvenanceArguments(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    dataset_id: uuid.UUID
    dimension: str | None = Field(default=None, min_length=1, max_length=255)
    measure: str | None = Field(default=None, min_length=1, max_length=255)
    aggregation: AggregationFunction | None = None
    scope: str = Field(default="FULL_DATASET", min_length=1, max_length=32)


class RunDecisionArguments(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    model_id: str = Field(min_length=1, max_length=128)
    province_code: str = Field(min_length=1, max_length=16)
    business_category: str = Field(min_length=1, max_length=128)
    mode: str = Field(default="PRODUCTION", pattern="^(PRODUCTION|EXPLORATORY)$")
    reference_year: int | None = Field(default=None, ge=1900, le=2100)
    criterion_weights: dict[str, float] = Field(default_factory=dict, max_length=20)


class IdentifyEvidenceGapsArguments(RunDecisionArguments):
    pass


class ToolDescriptor(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    name: str
    version: int
    description: str
    input_schema: dict[str, Any]
    required_permissions: list[str] = Field(default_factory=list)
    read_only: bool = True
    max_result_rows: int | None = None
