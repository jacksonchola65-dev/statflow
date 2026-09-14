"""
services/insight_engine.py
===========================

Deterministic Insight Engine for generating factual observations.

This service analyzes dataset structure, content, and patterns to generate
FACTUAL insights only. It does NOT make causal claims, predictions, or
business recommendations.

Design principles:
  - No speculation or inference beyond observable facts
  - All insights must be reproducible from data
  - Data quality observations are separate from metric insights
  - Confidence/status accurately reflects certainty
  - No arbitrary weighting or scoring
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from app.schemas.intelligence import (
    ConfidenceStatus,
    DataQualityNote,
    DataQualitySeverity,
    InsightResult,
    InsightType,
)

# ============================================================================
# Domain Models
# ============================================================================


@dataclass
class ColumnProfile:
    """Profile of a dataset column for insight analysis."""

    name: str
    data_type: str | None
    cardinality: int
    null_count: int
    total_count: int
    unique_values: dict[str, int] | None = None  # value -> count
    numeric_values: list[float | int] | None = None
    date_values: list[str] | None = None

    @property
    def null_percentage(self) -> float:
        """Percentage of values that are null."""
        if self.total_count == 0:
            return 0.0
        return (self.null_count / self.total_count) * 100

    @property
    def is_numeric(self) -> bool:
        """Check if column is numeric type."""
        dtype_str = str(self.data_type or "").lower()
        return any(t in dtype_str for t in ["integer", "decimal", "numeric", "float"])

    @property
    def is_temporal(self) -> bool:
        """Check if column is temporal type."""
        dtype_str = str(self.data_type or "").lower()
        return any(t in dtype_str for t in ["date", "datetime", "timestamp", "time"])


# ============================================================================
# Insight Generation Engine
# ============================================================================


class InsightEngine:
    """
    Deterministic insight generation from dataset profiles.

    Public methods:
      - generate_insights() — produce factual observations for a dataset
      - generate_data_quality_notes() — produce data quality observations
    """

    # Conservative limits to avoid overwhelming output
    MAX_INSIGHTS_PER_DATASET = 20
    MAX_QUALITY_NOTES_PER_DATASET = 15

    # Data quality thresholds
    HIGH_MISSINGNESS_THRESHOLD = 50.0  # percent
    LOW_COVERAGE_THRESHOLD = 10.0  # percent non-null

    def generate_insights(
        self,
        columns: Sequence[ColumnProfile],
        dataset_id: str | None = None,
    ) -> list[InsightResult]:
        """
        Generate factual observations about a dataset.

        Args:
            columns: Profile of each column
            dataset_id: Reference ID for the dataset

        Returns:
            List of InsightResult objects
        """
        if not columns:
            return []

        insights: list[InsightResult] = []
        source_ref = dataset_id or "unknown"

        # Numeric insights — highest/lowest values
        numeric_columns = [c for c in columns if c.is_numeric and c.numeric_values]
        for col in numeric_columns[:10]:  # limit processing
            insights.extend(self._generate_numeric_insights(col, source_ref))

        # Categorical insights — highest/lowest categories
        categorical_columns = [
            c for c in columns if not c.is_numeric and not c.is_temporal and c.unique_values
        ]
        for col in categorical_columns[:10]:  # limit processing
            insights.extend(self._generate_categorical_insights(col, source_ref))

        # Temporal insights — highest/lowest periods
        temporal_columns = [c for c in columns if c.is_temporal and c.date_values]
        for col in temporal_columns[:5]:  # limit processing
            insights.extend(self._generate_temporal_insights(col, source_ref))

        return insights[: self.MAX_INSIGHTS_PER_DATASET]

    def generate_data_quality_notes(
        self,
        columns: Sequence[ColumnProfile],
        dataset_id: str | None = None,
    ) -> list[DataQualityNote]:
        """
        Generate data quality observations.

        Args:
            columns: Profile of each column
            dataset_id: Reference ID for the dataset

        Returns:
            List of DataQualityNote objects
        """
        if not columns:
            return []

        notes: list[DataQualityNote] = []
        source_ref = dataset_id or "unknown"

        for col in columns:
            # Empty column
            if col.total_count == 0:
                notes.append(
                    DataQualityNote(
                        column=col.name,
                        observation=f"Column '{col.name}' contains no data rows.",
                        severity=DataQualitySeverity.WARNING,
                        affected_rows=0,
                        affected_percentage=0.0,
                        source_reference=source_ref,
                    )
                )
                continue

            # High missingness
            if col.null_percentage >= self.HIGH_MISSINGNESS_THRESHOLD:
                notes.append(
                    DataQualityNote(
                        column=col.name,
                        observation=f"Column '{col.name}' has high missingness ({col.null_percentage:.1f}% null).",
                        severity=DataQualitySeverity.WARNING,
                        affected_rows=col.null_count,
                        affected_percentage=col.null_percentage,
                        recommendation=f"Investigate null patterns in '{col.name}'. Consider whether this column is essential for analysis.",
                        source_reference=source_ref,
                    )
                )
                continue

            # Missing values present
            if col.null_count > 0:
                notes.append(
                    DataQualityNote(
                        column=col.name,
                        observation=f"Column '{col.name}' has missing values ({col.null_count} nulls, {col.null_percentage:.1f}%).",
                        severity=DataQualitySeverity.INFO,
                        affected_rows=col.null_count,
                        affected_percentage=col.null_percentage,
                        source_reference=source_ref,
                    )
                )

            # Low coverage (inverted view)
            non_null_percentage = 100.0 - col.null_percentage
            if non_null_percentage <= self.LOW_COVERAGE_THRESHOLD:
                notes.append(
                    DataQualityNote(
                        column=col.name,
                        observation=f"Column '{col.name}' has low coverage ({non_null_percentage:.1f}% non-null).",
                        severity=DataQualitySeverity.WARNING,
                        affected_rows=col.null_count,
                        affected_percentage=col.null_percentage,
                        source_reference=source_ref,
                    )
                )

        return notes[: self.MAX_QUALITY_NOTES_PER_DATASET]

    # ========================================================================
    # Numeric Column Insights
    # ========================================================================

    def _generate_numeric_insights(
        self,
        col: ColumnProfile,
        source_ref: str,
    ) -> list[InsightResult]:
        """Generate insights for a numeric measure column."""
        insights: list[InsightResult] = []

        if not col.numeric_values or len(col.numeric_values) == 0:
            return []

        values = [v for v in col.numeric_values if v is not None]
        if not values:
            return []

        # Highest value
        max_val = max(values)
        insights.append(
            InsightResult(
                insight_type=InsightType.HIGHEST_PERIOD
                if col.is_temporal
                else InsightType.LOWEST_CATEGORY,
                metric=col.name,
                subject=f"Maximum value in {col.name}",
                value=max_val,
                statement_data={"operation": "max", "column": col.name, "result": max_val},
                severity=DataQualitySeverity.INFO,
                confidence=ConfidenceStatus.SUPPORTED,
                source_reference=source_ref,
            )
        )

        # Lowest value
        min_val = min(values)
        insights.append(
            InsightResult(
                insight_type=InsightType.LOWEST_PERIOD
                if col.is_temporal
                else InsightType.LOWEST_CATEGORY,
                metric=col.name,
                subject=f"Minimum value in {col.name}",
                value=min_val,
                statement_data={"operation": "min", "column": col.name, "result": min_val},
                severity=DataQualitySeverity.INFO,
                confidence=ConfidenceStatus.SUPPORTED,
                source_reference=source_ref,
            )
        )

        return insights

    # ========================================================================
    # Categorical Dimension Insights
    # ========================================================================

    def _generate_categorical_insights(
        self,
        col: ColumnProfile,
        source_ref: str,
    ) -> list[InsightResult]:
        """Generate insights for a categorical dimension column."""
        insights: list[InsightResult] = []

        if not col.unique_values or len(col.unique_values) == 0:
            return []

        # Find highest category (most frequent)
        sorted_cats = sorted(col.unique_values.items(), key=lambda x: x[1], reverse=True)

        if sorted_cats:
            highest_cat, highest_count = sorted_cats[0]
            insights.append(
                InsightResult(
                    insight_type=InsightType.HIGHEST_CATEGORY,
                    metric=col.name,
                    dimension=col.name,
                    subject=highest_cat,
                    value=highest_count,
                    statement_data={
                        "operation": "highest_category",
                        "column": col.name,
                        "category": highest_cat,
                        "count": highest_count,
                    },
                    severity=DataQualitySeverity.INFO,
                    confidence=ConfidenceStatus.SUPPORTED,
                    source_reference=source_ref,
                )
            )

        # Find lowest category (least frequent)
        if len(sorted_cats) > 1:
            lowest_cat, lowest_count = sorted_cats[-1]
            insights.append(
                InsightResult(
                    insight_type=InsightType.LOWEST_CATEGORY,
                    metric=col.name,
                    dimension=col.name,
                    subject=lowest_cat,
                    value=lowest_count,
                    statement_data={
                        "operation": "lowest_category",
                        "column": col.name,
                        "category": lowest_cat,
                        "count": lowest_count,
                    },
                    severity=DataQualitySeverity.INFO,
                    confidence=ConfidenceStatus.SUPPORTED,
                    source_reference=source_ref,
                )
            )

        return insights

    # ========================================================================
    # Temporal Dimension Insights
    # ========================================================================

    def _generate_temporal_insights(
        self,
        col: ColumnProfile,
        source_ref: str,
    ) -> list[InsightResult]:
        """Generate insights for a temporal dimension column."""
        insights: list[InsightResult] = []

        if not col.date_values or len(col.date_values) == 0:
            return []

        # Only generate if we have ordered data
        sorted_dates = sorted(col.date_values)

        if sorted_dates:
            earliest = sorted_dates[0]
            insights.append(
                InsightResult(
                    insight_type=InsightType.HIGHEST_PERIOD,
                    metric=col.name,
                    subject=f"Earliest date in {col.name}",
                    value=earliest,
                    statement_data={"operation": "min_date", "column": col.name, "date": earliest},
                    severity=DataQualitySeverity.INFO,
                    confidence=ConfidenceStatus.SUPPORTED,
                    source_reference=source_ref,
                )
            )

            latest = sorted_dates[-1]
            insights.append(
                InsightResult(
                    insight_type=InsightType.LOWEST_PERIOD,
                    metric=col.name,
                    subject=f"Latest date in {col.name}",
                    value=latest,
                    statement_data={"operation": "max_date", "column": col.name, "date": latest},
                    severity=DataQualitySeverity.INFO,
                    confidence=ConfidenceStatus.SUPPORTED,
                    source_reference=source_ref,
                )
            )

        return insights
