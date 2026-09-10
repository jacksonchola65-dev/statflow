"""
services/data_intelligence_service.py
======================================

Dataset Intelligence Orchestration Service.

Orchestrates deterministic intelligence generation for an uploaded dataset.

Composes:
  - KPI generation
  - Insight generation
  - Data quality analysis
  - Column intelligence
  - Visualization recommendations

All results are deterministic and reproducible from the source data.

Design: Thin orchestrator over existing services. Does not duplicate logic.
"""

from __future__ import annotations

import time
import uuid
from typing import Any, Sequence

from app.schemas.intelligence import (
    ColumnIntelligence,
    ColumnSemanticType,
    ConfidenceStatus,
    DatasetIntelligenceResult,
)

from .insight_engine import ColumnProfile as InsightColumnProfile
from .insight_engine import InsightEngine
from .kpi_engine import ColumnProfile as KpiColumnProfile
from .kpi_engine import KpiEngine
from .visualization_recommendation_engine import (
    ColumnInfo,
    VisualizationRecommendationEngine,
)

# ============================================================================
# Service Exceptions
# ============================================================================


class DataIntelligenceError(Exception):
    """Raised when intelligence generation fails."""

    pass


class EmptyDatasetError(DataIntelligenceError):
    """Raised when dataset has no rows or columns."""

    pass


# ============================================================================
# Data Intelligence Service
# ============================================================================


class DataIntelligenceService:
    """
    Orchestrates deterministic intelligence generation for datasets.

    Public methods:
      - analyze_dataset() — generate complete intelligence for a dataset
    """

    def __init__(self):
        """Initialize sub-engines."""
        self.kpi_engine = KpiEngine()
        self.insight_engine = InsightEngine()
        self.visualization_engine = VisualizationRecommendationEngine()

    def analyze_dataset(
        self,
        dataset_id: str,
        columns: Sequence[dict[str, Any]],
        rows: list[dict[str, Any]] | None = None,
        row_count: int = 0,
    ) -> DatasetIntelligenceResult:
        """
        Generate complete intelligence for a dataset.

        Args:
            dataset_id: Unique dataset identifier (string or UUID)
            columns: List of column definitions (with type, role, etc.)
            rows: Optional raw row data for advanced analysis
            row_count: Total row count (may differ from len(rows) if rows are sampled)

        Returns:
            DatasetIntelligenceResult with all intelligence components

        Raises:
            EmptyDatasetError: If dataset has no columns or rows
            DataIntelligenceError: If any sub-engine fails
        """
        if not columns or row_count == 0:
            raise EmptyDatasetError("Cannot analyze empty dataset (no columns or rows).")

        if rows is None:
            rows = []

        # Convert dataset_id to UUID
        try:
            dataset_uuid = uuid.UUID(dataset_id) if isinstance(dataset_id, str) else dataset_id
        except (ValueError, AttributeError):
            dataset_uuid = uuid.UUID(str(dataset_id))

        start_time = time.time()
        try:
            # ── Build column profiles for sub-engines ────────────────────────
            kpi_columns = self._build_kpi_column_profiles(columns, rows)
            insight_columns = self._build_insight_column_profiles(columns, rows)
            viz_columns = self._build_viz_column_profiles(columns)

            # ── Generate intelligence components ──────────────────────────────
            kpis = self.kpi_engine.generate_kpis(kpi_columns, rows, dataset_id)
            insights = self.insight_engine.generate_insights(insight_columns, dataset_id)
            quality_notes = self.insight_engine.generate_data_quality_notes(insight_columns, dataset_id)
            viz_recommendations = self.visualization_engine.recommend(viz_columns, row_count, dataset_id)

            # ── Build column intelligence ────────────────────────────────────
            column_intelligence = self._build_column_intelligence(columns)

            # ── Assemble result ───────────────────────────────────────────────
            elapsed = time.time() - start_time

            return DatasetIntelligenceResult(
                dataset_id=dataset_uuid,
                row_count=row_count,
                column_count=len(columns),
                columns=column_intelligence,
                kpis=kpis,
                insights=insights,
                data_quality_notes=quality_notes,
                visualization_recommendations=viz_recommendations,
                provenance={
                    "dataset_id": str(dataset_uuid),
                    "column_count": len(columns),
                    "row_count": row_count,
                    "analysis_method": "deterministic_intelligence_v1",
                    "intelligence_components": [
                        "kpi_engine",
                        "insight_engine",
                        "visualization_recommendation_engine",
                        "semantic_pipeline",
                    ],
                },
                performance_metrics={
                    "total_analysis_seconds": round(elapsed, 3),
                    "kpi_count": len(kpis),
                    "insight_count": len(insights),
                    "quality_notes_count": len(quality_notes),
                    "visualization_recommendations_count": len(viz_recommendations),
                },
            )

        except Exception as exc:
            if isinstance(exc, DataIntelligenceError):
                raise
            raise DataIntelligenceError(f"Intelligence analysis failed: {exc}") from exc

    # ========================================================================
    # Column Profile Builders
    # ========================================================================

    def _build_kpi_column_profiles(
        self,
        columns: Sequence[dict[str, Any]],
        rows: list[dict[str, Any]],
    ) -> list[KpiColumnProfile]:
        """Build KPI engine column profiles."""
        profiles = []

        for col in columns:
            col_name = col.get("identifier") or col.get("name") or "unknown"
            data_type = col.get("data_type") or col.get("inferred_type")
            role = col.get("role")
            cardinality = col.get("cardinality", 0)
            null_count = col.get("null_count", 0)
            total_count = col.get("total_count", len(rows))

            # Extract numeric values if available
            numeric_values = None
            if col.get("is_numeric") or str(data_type or "").lower() in ["integer", "decimal"]:
                numeric_values = []
                for row in rows:
                    try:
                        val = row.get(col_name)
                        if val is not None:
                            numeric_values.append(float(val))
                    except (ValueError, TypeError):
                        pass

            profiles.append(
                KpiColumnProfile(
                    name=col_name,
                    data_type=data_type,
                    role=role,
                    cardinality=cardinality,
                    null_count=null_count,
                    total_count=total_count,
                    numeric_values=numeric_values,
                )
            )

        return profiles

    def _build_insight_column_profiles(
        self,
        columns: Sequence[dict[str, Any]],
        rows: list[dict[str, Any]],
    ) -> list[InsightColumnProfile]:
        """Build Insight engine column profiles."""
        profiles = []

        for col in columns:
            col_name = col.get("identifier") or col.get("name") or "unknown"
            data_type = col.get("data_type") or col.get("inferred_type")
            cardinality = col.get("cardinality", 0)
            null_count = col.get("null_count", 0)
            total_count = col.get("total_count", len(rows))

            # Extract unique values and their counts
            unique_values: dict[str, int] | None = None
            if str(data_type or "").lower() not in ["integer", "decimal"]:
                unique_values = {}
                for row in rows:
                    val = row.get(col_name)
                    if val is not None and val != "":
                        val_str = str(val)
                        unique_values[val_str] = unique_values.get(val_str, 0) + 1

            # Extract numeric values
            numeric_values = None
            if str(data_type or "").lower() in ["integer", "decimal"]:
                numeric_values = []
                for row in rows:
                    try:
                        val = row.get(col_name)
                        if val is not None:
                            numeric_values.append(float(val))
                    except (ValueError, TypeError):
                        pass

            # Extract date values
            date_values = None
            if str(data_type or "").lower() in ["date", "datetime"]:
                date_values = []
                for row in rows:
                    val = row.get(col_name)
                    if val is not None:
                        date_values.append(str(val))

            profiles.append(
                InsightColumnProfile(
                    name=col_name,
                    data_type=data_type,
                    cardinality=cardinality,
                    null_count=null_count,
                    total_count=total_count,
                    unique_values=unique_values,
                    numeric_values=numeric_values,
                    date_values=date_values,
                )
            )

        return profiles

    def _build_viz_column_profiles(
        self,
        columns: Sequence[dict[str, Any]],
    ) -> list[ColumnInfo]:
        """Build Visualization engine column profiles."""
        profiles = []

        for col in columns:
            col_id = col.get("identifier") or col.get("name") or "unknown"
            col_name = col.get("label") or col.get("display_name") or col_id
            data_type = col.get("data_type") or col.get("inferred_type")
            role = col.get("role")
            cardinality = col.get("cardinality", 0)

            profiles.append(
                ColumnInfo(
                    identifier=col_id,
                    name=col_name,
                    data_type=data_type,
                    role=role,
                    cardinality=cardinality,
                    sample_values=col.get("sample_values"),
                )
            )

        return profiles

    def _build_column_intelligence(
        self,
        columns: Sequence[dict[str, Any]],
    ) -> list[ColumnIntelligence]:
        """Build column intelligence from column metadata."""
        intelligence = []

        for col in columns:
            col_name = col.get("identifier") or col.get("name") or "unknown"
            physical_type = str(col.get("data_type") or col.get("inferred_type") or "UNKNOWN")

            # Map semantic understanding
            semantic_type = self._infer_semantic_type(physical_type, col.get("role"))
            semantic_hints = self._extract_semantic_hints(col.get("sample_values"))

            # Calculate null metrics
            null_count = col.get("null_count", 0)
            total_count = col.get("total_count", 1)
            null_percentage = (null_count / total_count * 100) if total_count > 0 else 0.0

            intelligence.append(
                ColumnIntelligence(
                    column_name=col_name,
                    physical_type=physical_type,
                    semantic_type=semantic_type,
                    semantic_hints=semantic_hints,
                    cardinality=col.get("cardinality", 0),
                    null_count=null_count,
                    null_percentage=null_percentage,
                    unique_values=col.get("sample_values"),
                    confidence=ConfidenceStatus.SUPPORTED,
                )
            )

        return intelligence

    # ========================================================================
    # Semantic Classification Helpers
    # ========================================================================

    def _infer_semantic_type(self, physical_type: str, role: str | None) -> ColumnSemanticType:
        """Infer semantic type from physical type and role."""
        dtype_str = str(physical_type or "").upper()

        if role == "measure" or any(t in dtype_str for t in ["INTEGER", "DECIMAL", "NUMERIC", "FLOAT"]):
            return ColumnSemanticType.NUMERIC_MEASURE

        if any(t in dtype_str for t in ["DATE", "DATETIME", "TIMESTAMP", "TIME"]):
            return ColumnSemanticType.TEMPORAL

        if "BOOLEAN" in dtype_str:
            return ColumnSemanticType.BOOLEAN

        if role == "dimension":
            return ColumnSemanticType.CATEGORICAL

        return ColumnSemanticType.TEXT

    def _extract_semantic_hints(self, sample_values: list[str] | None) -> list[Any]:
        """Extract semantic hints from sample values."""
        # Placeholder: would analyze sample values for hints like CURRENCY, PERCENTAGE, etc.
        # For now, return empty list
        return []
