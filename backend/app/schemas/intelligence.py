"""
schemas/intelligence.py
=======================

Pydantic v2 contracts for Data & Visualization Intelligence.

Contains:
  - KpiResult — individual KPI metric result
  - InsightResult — factual observation/insight
  - DataQualityNote — data quality observation
  - VisualizationRecommendation — chart type recommendation
  - ColumnIntelligence — semantic column understanding
  - DatasetIntelligenceResult — orchestrated intelligence for full dataset
"""

from __future__ import annotations

import uuid
from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class KpiType(str, Enum):
    """Supported KPI metric types."""

    TOTAL = "total"
    COUNT = "count"
    COUNT_DISTINCT = "count_distinct"
    AVERAGE = "average"
    MINIMUM = "minimum"
    MAXIMUM = "maximum"
    HIGHEST_CATEGORY = "highest_category"
    LOWEST_CATEGORY = "lowest_category"
    HIGHEST_PERIOD = "highest_period"
    LOWEST_PERIOD = "lowest_period"


class InsightType(str, Enum):
    """Supported insight types — factual observations only."""

    HIGHEST_CATEGORY = "highest_category"
    LOWEST_CATEGORY = "lowest_category"
    HIGHEST_PERIOD = "highest_period"
    LOWEST_PERIOD = "lowest_period"
    INCREASE_OVER_TIME = "increase_over_time"
    DECREASE_OVER_TIME = "decrease_over_time"
    MISSING_VALUES = "missing_values"
    HIGH_MISSINGNESS = "high_missingness"
    EMPTY_COLUMN = "empty_column"
    LOW_COVERAGE = "low_coverage"


class VisualizationType(str, Enum):
    """Supported visualization types."""

    KPI = "kpi"
    BAR = "bar"
    LINE = "line"
    AREA = "area"
    PIE = "pie"
    TABLE = "table"
    MAP = "map"


class ColumnSemanticType(str, Enum):
    """Semantic understanding of column purpose."""

    TEMPORAL = "temporal"
    CATEGORICAL = "categorical"
    NUMERIC_MEASURE = "numeric_measure"
    IDENTIFIER = "identifier"
    BOOLEAN = "boolean"
    GEOGRAPHIC_CANDIDATE = "geographic_candidate"
    TEXT = "text"
    UNKNOWN = "unknown"


class SemanticHint(str, Enum):
    """Semantic hints for further understanding."""

    CURRENCY = "currency"
    PERCENTAGE = "percentage"
    QUANTITY = "quantity"
    DATE = "date"
    YEAR = "year"
    CATEGORY = "category"
    LOCATION = "location"
    MONTH = "month"
    QUARTER = "quarter"


class DataQualitySeverity(str, Enum):
    """Severity level for data quality notes."""

    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"


class ConfidenceStatus(str, Enum):
    """Confidence status for uncertain determinations."""

    SUPPORTED = "supported"
    PARTIAL = "partial"
    AMBIGUOUS = "ambiguous"
    UNSUPPORTED = "unsupported"


class VisualizationRecommendationReason(str, Enum):
    """Reason codes for visualization recommendations."""

    TIME_SERIES_MEASURE = "time_series_measure"
    CATEGORY_COMPARISON = "category_comparison"
    PART_TO_WHOLE = "part_to_whole"
    SINGLE_AGGREGATE = "single_aggregate"
    GEOGRAPHIC_MEASURE = "geographic_measure"
    TABLE_FALLBACK = "table_fallback"
    AMBIGUOUS_SHAPE = "ambiguous_shape"


# ============================================================================
# KPI Result
# ============================================================================


class KpiResult(BaseModel):
    """
    A single KPI metric result derived from dataset analysis.

    All KPI values are deterministic and reproducible from the source data.
    """

    id: str = Field(default_factory=lambda: str(uuid.uuid4()), description="Unique KPI ID")
    label: str = Field(
        min_length=1, max_length=100, description="Display label (e.g. 'National Average')"
    )
    metric: str = Field(min_length=1, description="Metric name (e.g. 'revenue')")
    kpi_type: KpiType = Field(description="Type of KPI (total, average, highest_category, etc.)")
    aggregation: str = Field(
        min_length=1, description="Aggregation used (e.g. 'SUM', 'AVG', 'MAX')"
    )
    value: float | int | str | None = Field(description="The computed KPI value")
    unit: Optional[str] = Field(default=None, description="Unit suffix (e.g. '%', 'USD')")
    scope: Optional[str] = Field(
        default=None, description="Scope of aggregation (e.g. 'all_provinces', 'all_periods')"
    )
    dimension: Optional[str] = Field(
        default=None, description="Dimension if this KPI is grouped (e.g. 'province', 'month')"
    )
    dimension_value: Optional[str] = Field(
        default=None, description="Dimension value (e.g. 'Lusaka', 'January')"
    )
    period: Optional[str] = Field(
        default=None, description="Time period if temporal (e.g. '2024', '2024-01')"
    )
    source_reference: str = Field(
        description="Reference to data source (e.g. dataset_id, query_id)"
    )
    confidence: ConfidenceStatus = Field(
        default=ConfidenceStatus.SUPPORTED, description="Confidence in this KPI"
    )
    warnings: list[str] = Field(default_factory=list, description="Any warnings or caveats")
    analysis_scope: str = Field(default="FULL_DATASET", description="Truth scope of this value")
    sample_size: int | None = Field(default=None, ge=0)
    total_rows: int | None = Field(default=None, ge=0)
    coverage_ratio: float | None = Field(default=None, ge=0.0, le=1.0)
    created_at: datetime = Field(
        default_factory=datetime.utcnow, description="When this KPI was generated"
    )


# ============================================================================
# Insight Result
# ============================================================================


class InsightResult(BaseModel):
    """
    A factual observation about the dataset.

    Insights are deterministic statements of fact derived from the data.
    They do NOT make causal claims, predictions, or business recommendations.
    """

    id: str = Field(default_factory=lambda: str(uuid.uuid4()), description="Unique insight ID")
    insight_type: InsightType = Field(
        description="Type of insight (highest_category, increase_over_time, etc.)"
    )
    metric: str = Field(min_length=1, description="Metric being analyzed (e.g. 'revenue')")
    dimension: Optional[str] = Field(default=None, description="Dimension (e.g. 'branch', 'month')")
    subject: Optional[str] = Field(
        default=None, description="Subject of observation (e.g. category name, period)"
    )
    value: float | int | str | None = Field(description="Primary value")
    comparison_value: Optional[float | int | str] = Field(
        default=None, description="Secondary value for comparison"
    )
    change: Optional[float] = Field(
        default=None, description="Change amount or percentage (if applicable)"
    )
    period: Optional[str] = Field(default=None, description="Time period (if temporal)")
    comparison_period: Optional[str] = Field(
        default=None, description="Period being compared to (if temporal)"
    )
    statement_data: dict[str, Any] = Field(
        default_factory=dict,
        description="Structured data representing this insight (for reproducibility)",
    )
    severity: DataQualitySeverity = Field(
        default=DataQualitySeverity.INFO, description="Severity level (info/warning/critical)"
    )
    confidence: ConfidenceStatus = Field(
        default=ConfidenceStatus.SUPPORTED, description="Confidence in this insight"
    )
    source_reference: str = Field(
        description="Reference to data source (e.g. dataset_id, query_id)"
    )
    warnings: list[str] = Field(default_factory=list, description="Warnings about this insight")
    analysis_scope: str = Field(default="FULL_DATASET", description="Truth scope of this insight")
    sample_size: int | None = Field(default=None, ge=0)
    total_rows: int | None = Field(default=None, ge=0)
    coverage_ratio: float | None = Field(default=None, ge=0.0, le=1.0)
    created_at: datetime = Field(
        default_factory=datetime.utcnow, description="When this insight was generated"
    )


# ============================================================================
# Data Quality Notes
# ============================================================================


class DataQualityNote(BaseModel):
    """
    Observation about data quality in the dataset.

    Examples: missing values, low coverage, empty columns.
    """

    id: str = Field(default_factory=lambda: str(uuid.uuid4()), description="Unique note ID")
    column: Optional[str] = Field(default=None, description="Column name if applicable")
    observation: str = Field(min_length=1, description="Description of the observation")
    severity: DataQualitySeverity = Field(description="Severity level")
    affected_rows: Optional[int] = Field(default=None, description="Number of affected rows")
    affected_percentage: Optional[float] = Field(
        default=None, description="Percentage of affected rows"
    )
    recommendation: Optional[str] = Field(default=None, description="Recommended action if any")
    source_reference: str = Field(description="Reference to data source")
    analysis_scope: str = Field(default="FULL_DATASET", description="Truth scope of this note")
    sample_size: int | None = Field(default=None, ge=0)
    total_rows: int | None = Field(default=None, ge=0)
    coverage_ratio: float | None = Field(default=None, ge=0.0, le=1.0)
    created_at: datetime = Field(
        default_factory=datetime.utcnow, description="When this note was generated"
    )


# ============================================================================
# Column Intelligence
# ============================================================================


class ColumnIntelligence(BaseModel):
    """
    Semantic understanding of a single column.

    Combines type inference with semantic detection.
    """

    column_name: str = Field(min_length=1, description="Column identifier")
    physical_type: str = Field(description="Physical data type (INTEGER, TEXT, DATE, etc.)")
    semantic_type: ColumnSemanticType = Field(
        description="Semantic interpretation (TEMPORAL, CATEGORICAL, NUMERIC_MEASURE, etc.)"
    )
    semantic_hints: list[SemanticHint] = Field(
        default_factory=list, description="Additional semantic hints (CURRENCY, PERCENTAGE, etc.)"
    )
    cardinality: int = Field(ge=0, description="Distinct value count")
    null_count: int = Field(ge=0, description="Number of null/missing values")
    null_percentage: float = Field(ge=0.0, le=100.0, description="Percentage of null values")
    unique_values: Optional[list[str]] = Field(
        default=None, description="Sample unique values (limited)"
    )
    confidence: ConfidenceStatus = Field(
        default=ConfidenceStatus.SUPPORTED, description="Confidence in this classification"
    )
    warnings: list[str] = Field(default_factory=list, description="Any warnings about this column")


# ============================================================================
# Visualization Recommendation
# ============================================================================


class VisualizationRecommendation(BaseModel):
    """
    Recommendation for visualizing a dataset or query result.

    Provides both the recommended chart type and compatible alternatives.
    """

    id: str = Field(
        default_factory=lambda: str(uuid.uuid4()), description="Unique recommendation ID"
    )
    visualization_type: VisualizationType = Field(description="Recommended chart type")
    title: Optional[str] = Field(default=None, description="Suggested chart title")
    dimension: Optional[str] = Field(
        default=None, description="Recommended dimension/category field"
    )
    measure: Optional[str] = Field(default=None, description="Recommended measure/value field")
    aggregation: Optional[str] = Field(
        default=None, description="Recommended aggregation if applicable"
    )
    series: list[str] = Field(
        default_factory=list, description="Series fields for multi-series charts"
    )
    filters: dict[str, Any] = Field(default_factory=dict, description="Recommended filters")
    reason_code: VisualizationRecommendationReason = Field(
        description="Reason for this recommendation"
    )
    confidence: ConfidenceStatus = Field(
        default=ConfidenceStatus.SUPPORTED, description="Confidence in recommendation"
    )
    compatible_types: list[VisualizationType] = Field(
        default_factory=list, description="Other compatible visualization types"
    )
    warnings: list[str] = Field(
        default_factory=list, description="Warnings (e.g., high cardinality, missing values)"
    )
    created_at: datetime = Field(
        default_factory=datetime.utcnow, description="When this recommendation was generated"
    )


# ============================================================================
# Dataset Intelligence Result
# ============================================================================


class DatasetIntelligenceResult(BaseModel):
    """
    Orchestrated intelligence for a complete dataset.

    This is the primary output of the "analyze dataset" operation.
    All components are deterministic and reproducible.
    """

    dataset_id: uuid.UUID = Field(description="Dataset being analyzed")
    analysis_timestamp: datetime = Field(
        default_factory=datetime.utcnow, description="When analysis was performed"
    )

    # Dataset metadata
    row_count: int = Field(ge=0, description="Number of data rows")
    column_count: int = Field(ge=0, description="Number of columns")
    columns: list[ColumnIntelligence] = Field(
        default_factory=list, description="Intelligence for each column"
    )

    # KPIs
    kpis: list[KpiResult] = Field(default_factory=list, description="Generated KPI metrics")

    # Insights
    insights: list[InsightResult] = Field(default_factory=list, description="Factual observations")
    data_quality_notes: list[DataQualityNote] = Field(
        default_factory=list, description="Data quality observations"
    )

    # Visualization recommendations
    visualization_recommendations: list[VisualizationRecommendation] = Field(
        default_factory=list, description="Chart type recommendations"
    )

    # Metadata
    provenance: dict[str, Any] = Field(
        default_factory=dict, description="Provenance and reproducibility information"
    )
    warnings: list[str] = Field(default_factory=list, description="Any analysis-level warnings")
    performance_metrics: dict[str, Any] = Field(
        default_factory=dict, description="Performance info (processing time, etc.)"
    )

    class Config:
        use_enum_values = True


class IntelligenceDatasetSummary(BaseModel):
    """Stable dataset metadata shown by the intelligence workspace."""

    id: uuid.UUID
    name: str
    row_count: int
    column_count: int
    imported_at: datetime | None = None


class VisualizationArtifact(BaseModel):
    """A renderable, backend-authoritative visualization result."""

    id: str
    type: VisualizationType
    title: str
    reason_code: VisualizationRecommendationReason
    dimension: dict[str, str] | None = None
    measure: dict[str, str] | None = None
    series: list[str] = Field(default_factory=list)
    data: list[dict[str, Any]] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    provenance: dict[str, Any] = Field(default_factory=dict)
    analysis_scope: str = Field(default="FULL_DATASET")
    sample_size: int | None = Field(default=None, ge=0)
    total_rows: int | None = Field(default=None, ge=0)
    coverage_ratio: float | None = Field(default=None, ge=0.0, le=1.0)


class DatasetIntelligenceResponse(BaseModel):
    """Production response for analysis of a persisted dataset."""

    dataset: IntelligenceDatasetSummary
    profile: dict[str, Any] = Field(default_factory=dict)
    kpis: list[KpiResult] = Field(default_factory=list)
    visualizations: list[VisualizationArtifact] = Field(default_factory=list)
    insights: list[InsightResult] = Field(default_factory=list)
    quality_notes: list[DataQualityNote] = Field(default_factory=list)
    provenance: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    analysis_scope: str = Field(default="FULL_DATASET")
    sample_size: int = Field(default=0, ge=0)
    total_rows: int = Field(default=0, ge=0)
    coverage_ratio: float = Field(default=0.0, ge=0.0, le=1.0)
