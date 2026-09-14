"""
services/kpi_engine.py
======================

Deterministic KPI (Key Performance Indicator) generation service.

This service derives appropriate KPI candidates from dataset structure,
column semantics, and data content. All KPIs are exact calculations
reproducible from authoritative data.

Design principles:
  - No manufactured/inferred business meaning (e.g., don't assume numeric = revenue)
  - Use neutral labels for uncertain semantics
  - Respect column roles (dimension, measure, identifier)
  - Handle edge cases (empty datasets, all nulls, etc.)
  - Return exact, calculable values (never estimates)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Sequence

from app.models.ingestion import InferredColumnType
from app.schemas.intelligence import (
    ConfidenceStatus,
    KpiResult,
    KpiType,
)

# ============================================================================
# Domain Models
# ============================================================================


@dataclass
class ColumnProfile:
    """Profile of a dataset column for KPI analysis."""

    name: str
    data_type: InferredColumnType | str
    role: str | None  # 'dimension', 'measure', 'identifier', or None
    cardinality: int
    null_count: int
    total_count: int
    numeric_values: list[float | int] | None = None
    unique_non_null_values: set[Any] | None = None

    @property
    def null_percentage(self) -> float:
        """Percentage of values that are null."""
        if self.total_count == 0:
            return 0.0
        return (self.null_count / self.total_count) * 100

    @property
    def is_numeric(self) -> bool:
        """Check if column is numeric type."""
        dtype_str = str(self.data_type).lower()
        return any(t in dtype_str for t in ["integer", "decimal", "numeric", "float"])

    @property
    def is_temporal(self) -> bool:
        """Check if column is temporal type."""
        dtype_str = str(self.data_type).lower()
        return any(t in dtype_str for t in ["date", "datetime", "timestamp", "time"])

    @property
    def is_measure(self) -> bool:
        """Check if column is likely a measure."""
        return (self.role == "measure") or (self.is_numeric and self.role != "dimension")

    @property
    def is_dimension(self) -> bool:
        """Check if column is likely a dimension."""
        return (self.role == "dimension") or (not self.is_numeric and self.role != "measure")


# ============================================================================
# KPI Generation Engine
# ============================================================================


class KpiEngine:
    """
    Deterministic KPI generation from dataset profiles.

    Public methods:
      - generate_kpis() — produce KPI candidates for a dataset
    """

    # Conservative limits to avoid overwhelming output
    MAX_NUMERIC_KPIS_PER_DATASET = 12
    MAX_CATEGORY_KPIS_PER_DATASET = 8
    MAX_CATEGORY_VALUES_TO_CONSIDER = 20  # for highest/lowest category KPIs

    def generate_kpis(
        self,
        columns: Sequence[ColumnProfile],
        rows_data: list[dict[str, Any]] | None = None,
        dataset_id: str | None = None,
    ) -> list[KpiResult]:
        """
        Generate appropriate KPI candidates for a dataset.

        Args:
            columns: Profile of each column
            rows_data: Optional raw data for advanced calculations
            dataset_id: Reference ID for the dataset

        Returns:
            List of KpiResult objects
        """
        if not columns:
            return []

        if rows_data is None:
            rows_data = []

        kpis: list[KpiResult] = []

        # Generate KPIs for numeric measures
        numeric_columns = [c for c in columns if c.is_numeric and c.role != "identifier"]
        for col in numeric_columns:
            if len(kpis) >= self.MAX_NUMERIC_KPIS_PER_DATASET:
                break

            kpis.extend(self._generate_numeric_kpis(col, rows_data, dataset_id))

        # Generate KPIs for categorical dimensions
        category_columns = [c for c in columns if c.is_dimension and not c.is_temporal]
        for col in category_columns:
            if len(kpis) >= self.MAX_NUMERIC_KPIS_PER_DATASET + self.MAX_CATEGORY_KPIS_PER_DATASET:
                break

            kpis.extend(self._generate_category_kpis(col, rows_data, dataset_id))

        # Generate KPIs for temporal dimensions (if paired with measures)
        temporal_columns = [c for c in columns if c.is_temporal]
        if temporal_columns and numeric_columns and rows_data:
            kpis.extend(
                self._generate_temporal_kpis(
                    temporal_columns, numeric_columns, rows_data, dataset_id
                )
            )

        return kpis[: self.MAX_NUMERIC_KPIS_PER_DATASET + self.MAX_CATEGORY_KPIS_PER_DATASET]

    # ========================================================================
    # Numeric Column KPIs
    # ========================================================================

    def _generate_numeric_kpis(
        self,
        col: ColumnProfile,
        rows_data: list[dict[str, Any]],
        dataset_id: str | None,
    ) -> list[KpiResult]:
        """Generate KPIs for a numeric measure column."""
        kpis: list[KpiResult] = []

        if not col.numeric_values or len(col.numeric_values) == 0:
            return []

        values = [v for v in col.numeric_values if v is not None]
        if not values:
            return []

        source_ref = dataset_id or col.name

        # Total
        total_val = sum(values)
        kpis.append(
            KpiResult(
                label=f"Total {col.name}",
                metric=col.name,
                kpi_type=KpiType.TOTAL,
                aggregation="SUM",
                value=self._format_numeric(total_val),
                scope="all_rows",
                source_reference=source_ref,
                confidence=ConfidenceStatus.SUPPORTED,
            )
        )

        # Count
        kpis.append(
            KpiResult(
                label=f"Count (non-null {col.name})",
                metric=col.name,
                kpi_type=KpiType.COUNT,
                aggregation="COUNT",
                value=len(values),
                scope="all_rows",
                source_reference=source_ref,
                confidence=ConfidenceStatus.SUPPORTED,
            )
        )

        # Average
        if len(values) > 0:
            avg_val = sum(values) / len(values)
            kpis.append(
                KpiResult(
                    label=f"Average {col.name}",
                    metric=col.name,
                    kpi_type=KpiType.AVERAGE,
                    aggregation="AVG",
                    value=self._format_numeric(avg_val),
                    scope="all_rows",
                    source_reference=source_ref,
                    confidence=ConfidenceStatus.SUPPORTED,
                )
            )

        # Minimum
        min_val = min(values)
        kpis.append(
            KpiResult(
                label=f"Minimum {col.name}",
                metric=col.name,
                kpi_type=KpiType.MINIMUM,
                aggregation="MIN",
                value=self._format_numeric(min_val),
                scope="all_rows",
                source_reference=source_ref,
                confidence=ConfidenceStatus.SUPPORTED,
            )
        )

        # Maximum
        max_val = max(values)
        kpis.append(
            KpiResult(
                label=f"Maximum {col.name}",
                metric=col.name,
                kpi_type=KpiType.MAXIMUM,
                aggregation="MAX",
                value=self._format_numeric(max_val),
                scope="all_rows",
                source_reference=source_ref,
                confidence=ConfidenceStatus.SUPPORTED,
            )
        )

        # Distinct count (if cardinality is reasonable)
        if col.cardinality > 0 and col.cardinality <= 100:
            kpis.append(
                KpiResult(
                    label=f"Distinct values in {col.name}",
                    metric=col.name,
                    kpi_type=KpiType.COUNT_DISTINCT,
                    aggregation="COUNT_DISTINCT",
                    value=col.cardinality,
                    scope="all_rows",
                    source_reference=source_ref,
                    confidence=ConfidenceStatus.SUPPORTED,
                )
            )

        return kpis

    # ========================================================================
    # Categorical Dimension KPIs
    # ========================================================================

    def _generate_category_kpis(
        self,
        col: ColumnProfile,
        rows_data: list[dict[str, Any]],
        dataset_id: str | None,
    ) -> list[KpiResult]:
        """Generate KPIs for a categorical dimension column."""
        kpis: list[KpiResult] = []

        if not rows_data or col.cardinality == 0:
            return []

        source_ref = dataset_id or col.name

        # Cardinality (distinct count)
        kpis.append(
            KpiResult(
                label=f"Distinct categories in {col.name}",
                metric=col.name,
                kpi_type=KpiType.COUNT_DISTINCT,
                aggregation="COUNT_DISTINCT",
                value=col.cardinality,
                scope="all_rows",
                source_reference=source_ref,
                confidence=ConfidenceStatus.SUPPORTED,
            )
        )

        # Most common category (highest frequency)
        if col.cardinality <= self.MAX_CATEGORY_VALUES_TO_CONSIDER:
            category_counts: dict[str, int] = {}
            for row in rows_data:
                val = row.get(col.name)
                if val is not None:
                    key = str(val)
                    category_counts[key] = category_counts.get(key, 0) + 1

            if category_counts:
                most_common = max(category_counts.items(), key=lambda x: x[1])
                kpis.append(
                    KpiResult(
                        label=f"Most common {col.name}",
                        metric=col.name,
                        kpi_type=KpiType.HIGHEST_CATEGORY,
                        aggregation="MODE",
                        value=most_common[0],
                        dimension=col.name,
                        dimension_value=most_common[0],
                        scope="all_rows",
                        source_reference=source_ref,
                        confidence=ConfidenceStatus.SUPPORTED,
                    )
                )

                # Least common category (lowest frequency)
                least_common = min(category_counts.items(), key=lambda x: x[1])
                kpis.append(
                    KpiResult(
                        label=f"Least common {col.name}",
                        metric=col.name,
                        kpi_type=KpiType.LOWEST_CATEGORY,
                        aggregation="MIN_FREQUENCY",
                        value=least_common[0],
                        dimension=col.name,
                        dimension_value=least_common[0],
                        scope="all_rows",
                        source_reference=source_ref,
                        confidence=ConfidenceStatus.SUPPORTED,
                    )
                )

        return kpis

    # ========================================================================
    # Temporal Dimension KPIs
    # ========================================================================

    def _generate_temporal_kpis(
        self,
        temporal_columns: list[ColumnProfile],
        numeric_columns: list[ColumnProfile],
        rows_data: list[dict[str, Any]],
        dataset_id: str | None,
    ) -> list[KpiResult]:
        """
        Generate time-based KPIs (highest/lowest by period).

        This is conservative — only generates insights when clear patterns exist.
        """
        kpis: list[KpiResult] = []

        if not rows_data or not temporal_columns or not numeric_columns:
            return []

        source_ref = dataset_id or "dataset"
        time_col = temporal_columns[0]
        measure_col = numeric_columns[0]

        # Build time-series aggregation
        time_series: dict[str, list[float]] = {}
        for row in rows_data:
            time_val = row.get(time_col.name)
            measure_val = row.get(measure_col.name)

            if time_val is not None and measure_val is not None:
                try:
                    measure_num = float(measure_val)
                    time_key = str(time_val)
                    if time_key not in time_series:
                        time_series[time_key] = []
                    time_series[time_key].append(measure_num)
                except (ValueError, TypeError):
                    continue

        if len(time_series) < 2:
            return []

        # Calculate aggregate per period
        period_aggregates = {period: sum(vals) / len(vals) for period, vals in time_series.items()}
        sorted_periods = sorted(period_aggregates.items(), key=lambda x: str(x[0]))

        if len(sorted_periods) >= 2:
            # Highest period
            highest = max(period_aggregates.items(), key=lambda x: x[1])
            kpis.append(
                KpiResult(
                    label=f"Highest {measure_col.name} by {time_col.name}",
                    metric=measure_col.name,
                    kpi_type=KpiType.HIGHEST_PERIOD,
                    aggregation="MAX",
                    value=self._format_numeric(highest[1]),
                    period=str(highest[0]),
                    dimension=time_col.name,
                    source_reference=source_ref,
                    confidence=ConfidenceStatus.SUPPORTED,
                )
            )

            # Lowest period
            lowest = min(period_aggregates.items(), key=lambda x: x[1])
            kpis.append(
                KpiResult(
                    label=f"Lowest {measure_col.name} by {time_col.name}",
                    metric=measure_col.name,
                    kpi_type=KpiType.LOWEST_PERIOD,
                    aggregation="MIN",
                    value=self._format_numeric(lowest[1]),
                    period=str(lowest[0]),
                    dimension=time_col.name,
                    source_reference=source_ref,
                    confidence=ConfidenceStatus.SUPPORTED,
                )
            )

        return kpis

    # ========================================================================
    # Utilities
    # ========================================================================

    @staticmethod
    def _format_numeric(value: float | int) -> str | float | int:
        """Format numeric values for display."""
        if isinstance(value, int) or value == int(value):
            return int(value)
        # Round to 2 decimal places for floats
        return round(float(value), 2)
