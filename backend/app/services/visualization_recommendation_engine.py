"""
services/visualization_recommendation_engine.py
==================================================

Deterministic Visualization Recommendation Engine.

Analyzes dataset/query result structure to recommend appropriate visualization
types based on column semantics, cardinality, temporal dimensions, etc.

Design principles:
  - Mirror frontend visualizationRules.js logic
  - Conservative pie chart governance (non-negative, limited cardinality)
  - Never recommend unsupported chart types
  - Reason codes over free-form text
  - Confidence reflects data shape certainty, not accuracy
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence

from app.schemas.intelligence import (
    ConfidenceStatus,
    VisualizationRecommendation,
    VisualizationRecommendationReason,
    VisualizationType,
)

# ============================================================================
# Domain Models
# ============================================================================


@dataclass
class ColumnInfo:
    """Information about a column in a result/dataset."""

    identifier: str
    name: str
    data_type: str | None = None
    role: str | None = None  # 'dimension', 'measure', or None
    cardinality: int = 0
    sample_values: list[Any] | None = None

    @property
    def is_numeric(self) -> bool:
        """Check if column is numeric."""
        dtype_str = str(self.data_type or "").lower()
        return any(t in dtype_str for t in ["integer", "decimal", "numeric", "float"])

    @property
    def is_temporal(self) -> bool:
        """Check if column is temporal."""
        dtype_str = str(self.data_type or "").lower()
        return any(t in dtype_str for t in ["date", "datetime", "timestamp", "time"])

    @property
    def is_measure(self) -> bool:
        """Check if column is a measure."""
        return self.role == "measure" or (self.is_numeric and self.role != "dimension")

    @property
    def is_dimension(self) -> bool:
        """Check if column is a dimension."""
        return self.role == "dimension" or (not self.is_numeric and self.role != "measure")


# ============================================================================
# Visualization Recommendation Engine
# ============================================================================


class VisualizationRecommendationEngine:
    """
    Deterministic visualization recommendation generator.

    Public methods:
      - recommend() — produce visualization recommendation for a result/dataset
    """

    # Conservative limits
    MAX_PIE_CARDINALITY = 10
    MIN_PIE_NONZERO_RATIO = 0.0  # Allow zero, but no negatives

    # Governa geography recommendations
    TRUSTED_GEOGRAPHIES = {"zambia_province", "zambia_district"}

    def recommend(
        self,
        columns: Sequence[ColumnInfo],
        row_count: int = 0,
        result_id: str | None = None,
    ) -> list[VisualizationRecommendation]:
        """
        Recommend visualization types for a result/dataset.

        Args:
            columns: List of columns in the result
            row_count: Number of data rows
            result_id: Reference ID for the result

        Returns:
            List of VisualizationRecommendation objects (highest confidence first)
        """
        if not columns or row_count == 0:
            return [
                VisualizationRecommendation(
                    visualization_type=VisualizationType.TABLE,
                    reason_code=VisualizationRecommendationReason.TABLE_FALLBACK,
                    confidence=ConfidenceStatus.SUPPORTED,
                    warnings=["Empty result; table is the only safe visualization."],
                )
            ]

        recommendations: list[VisualizationRecommendation] = []

        # Classify columns
        measures = [c for c in columns if c.is_measure]
        time_dims = [c for c in columns if c.is_dimension and c.is_temporal]
        cat_dims = [c for c in columns if c.is_dimension and not c.is_temporal]

        # Check if aggregate-only (all measures, single row)
        is_aggregate_only = all(c.is_measure for c in columns) if columns else False
        is_single_aggregate = is_aggregate_only and row_count == 1

        # 1. KPI visualization (single aggregate)
        if is_single_aggregate and measures:
            recommendations.append(
                VisualizationRecommendation(
                    visualization_type=VisualizationType.KPI,
                    reason_code=VisualizationRecommendationReason.SINGLE_AGGREGATE,
                    confidence=ConfidenceStatus.SUPPORTED,
                    measure=measures[0].identifier if measures else None,
                )
            )

        # 2. TIME SERIES — line or area (temporal dimension + measure)
        if time_dims and measures and row_count > 1:
            recommendations.append(
                VisualizationRecommendation(
                    visualization_type=VisualizationType.LINE,
                    reason_code=VisualizationRecommendationReason.TIME_SERIES_MEASURE,
                    confidence=ConfidenceStatus.SUPPORTED,
                    dimension=time_dims[0].identifier,
                    measure=measures[0].identifier,
                    compatible_types=[VisualizationType.AREA],
                )
            )

        # 3. CATEGORY COMPARISON — bar (categorical dimension + measure)
        if cat_dims and measures and row_count > 1:
            recommendations.append(
                VisualizationRecommendation(
                    visualization_type=VisualizationType.BAR,
                    reason_code=VisualizationRecommendationReason.CATEGORY_COMPARISON,
                    confidence=ConfidenceStatus.SUPPORTED,
                    dimension=cat_dims[0].identifier,
                    measure=measures[0].identifier,
                )
            )

        # 4. PIE CHART — part-to-whole (single category + single measure, limited cardinality)
        if self._is_pie_eligible(cat_dims, measures, row_count):
            recommendations.append(
                VisualizationRecommendation(
                    visualization_type=VisualizationType.PIE,
                    reason_code=VisualizationRecommendationReason.PART_TO_WHOLE,
                    confidence=ConfidenceStatus.SUPPORTED,
                    dimension=cat_dims[0].identifier,
                    measure=measures[0].identifier,
                )
            )

        # 5. GEOGRAPHIC MAP — for trusted geographies (deferred: low implementation surface)
        # Placeholder: Would check for geography-semantics column
        # if self._is_map_eligible(columns, measures):
        #     recommendations.append(...)

        # 6. TABLE FALLBACK
        if not recommendations:
            recommendations.append(
                VisualizationRecommendation(
                    visualization_type=VisualizationType.TABLE,
                    reason_code=VisualizationRecommendationReason.TABLE_FALLBACK,
                    confidence=ConfidenceStatus.SUPPORTED,
                    warnings=["Result shape does not match common visualization patterns. Table recommended."],
                )
            )

        return recommendations

    # ========================================================================
    # Helper Methods
    # ========================================================================

    def _is_pie_eligible(
        self,
        cat_dims: list[ColumnInfo],
        measures: list[ColumnInfo],
        row_count: int,
    ) -> bool:
        """
        Check if pie chart is eligible for this result.

        Requirements:
          - Exactly one categorical dimension
          - Exactly one measure
          - Cardinality <= MAX_PIE_CARDINALITY
          - Row count > 0 and <= MAX_PIE_CARDINALITY
          - All values non-negative
        """
        if len(cat_dims) != 1 or len(measures) != 1:
            return False

        dim = cat_dims[0]
        measure = measures[0]

        if row_count <= 0 or row_count > self.MAX_PIE_CARDINALITY:
            return False

        if dim.cardinality > self.MAX_PIE_CARDINALITY:
            return False

        # Sample values check: ensure measure values are non-negative
        # (In production, would validate actual data)
        # For now, conservative: assume safe if no clear negatives in sample
        if measure.sample_values:
            for val in measure.sample_values:
                if val is None or val == "":
                    continue
                try:
                    num_val = float(val) if isinstance(val, str) else val
                    if num_val < 0:
                        return False
                except (ValueError, TypeError):
                    pass

        return True

    def _is_map_eligible(
        self,
        columns: Sequence[ColumnInfo],
        measures: list[ColumnInfo],
    ) -> bool:
        """
        Check if map visualization is eligible.

        Currently very conservative: only for trusted geographies.
        """
        if not measures:
            return False

        # Placeholder: would check for geography-semantics metadata
        # or column naming patterns like "zambia_province"
        return False
