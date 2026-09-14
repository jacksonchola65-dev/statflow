"""
tests/test_visualization_recommendation_engine.py
===================================================

Test suite for VisualizationRecommendationEngine.

Tests validate that visualization recommendations are deterministic and
respect conservative governance (especially for pie charts).
"""

import pytest
from app.schemas.intelligence import (
    ConfidenceStatus,
    VisualizationRecommendationReason,
    VisualizationType,
)
from app.services.visualization_recommendation_engine import (
    ColumnInfo,
    VisualizationRecommendationEngine,
)

# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def viz_engine():
    """Create VisualizationRecommendationEngine instance."""
    return VisualizationRecommendationEngine()


@pytest.fixture
def time_dimension():
    """Sample temporal dimension column."""
    return ColumnInfo(
        identifier="date_col",
        name="Date",
        data_type="DATE",
        role="dimension",
        cardinality=6,
        sample_values=["2024-01-01", "2024-02-01", "2024-03-01"],
    )


@pytest.fixture
def numeric_measure():
    """Sample numeric measure column."""
    return ColumnInfo(
        identifier="revenue_col",
        name="Revenue",
        data_type="DECIMAL",
        role="measure",
        cardinality=24,
        sample_values=["1050.00", "1125.00", "1500.00"],
    )


@pytest.fixture
def category_dimension_low_card():
    """Sample low-cardinality categorical dimension."""
    return ColumnInfo(
        identifier="branch_col",
        name="Branch",
        data_type="TEXT",
        role="dimension",
        cardinality=2,
        sample_values=["Lusaka", "Ndola"],
    )


@pytest.fixture
def category_dimension_high_card():
    """Sample high-cardinality categorical dimension."""
    return ColumnInfo(
        identifier="product_col",
        name="Product",
        data_type="TEXT",
        role="dimension",
        cardinality=50,
        sample_values=[f"Product_{i}" for i in range(50)],
    )


# ============================================================================
# KPI (Single Aggregate) Tests
# ============================================================================


class TestKpiRecommendation:
    """Test KPI visualization recommendations."""

    def test_single_measure_aggregate_recommends_kpi(self, viz_engine, numeric_measure):
        """Single measure aggregate should recommend KPI."""
        recs = viz_engine.recommend([numeric_measure], row_count=1, result_id="result_001")

        assert len(recs) > 0
        assert any(r.visualization_type == VisualizationType.KPI for r in recs)
        kpi_rec = [r for r in recs if r.visualization_type == VisualizationType.KPI][0]
        assert kpi_rec.reason_code == VisualizationRecommendationReason.SINGLE_AGGREGATE

    def test_multiple_measures_does_not_recommend_kpi(self, viz_engine):
        """Multiple measures with dimension should not recommend KPI."""
        measure1 = ColumnInfo(
            identifier="revenue_col",
            name="Revenue",
            data_type="DECIMAL",
            role="measure",
            cardinality=24,
        )
        dimension = ColumnInfo(
            identifier="branch_col",
            name="Branch",
            data_type="TEXT",
            role="dimension",
            cardinality=2,
        )
        recs = viz_engine.recommend([dimension, measure1], row_count=2, result_id="result_001")

        # Should not be KPI since we have dimension + measure, not pure aggregate
        # KPI is only for all-measures single-row results
        assert not any(r.visualization_type == VisualizationType.KPI for r in recs)


# ============================================================================
# Time Series Tests
# ============================================================================


class TestTimeSeriesRecommendation:
    """Test time series (line/area) recommendations."""

    def test_temporal_dimension_and_measure_recommends_line(
        self, viz_engine, time_dimension, numeric_measure
    ):
        """Time dimension + measure should recommend line chart."""
        columns = [time_dimension, numeric_measure]
        recs = viz_engine.recommend(columns, row_count=6, result_id="result_001")

        assert any(r.visualization_type == VisualizationType.LINE for r in recs)
        line_rec = [r for r in recs if r.visualization_type == VisualizationType.LINE][0]
        assert line_rec.reason_code == VisualizationRecommendationReason.TIME_SERIES_MEASURE
        assert VisualizationType.AREA in line_rec.compatible_types

    def test_temporal_dimension_single_row_no_line(
        self, viz_engine, time_dimension, numeric_measure
    ):
        """Time dimension with only one row should not recommend line."""
        columns = [time_dimension, numeric_measure]
        recs = viz_engine.recommend(columns, row_count=1, result_id="result_001")

        # Single row, should not recommend line
        assert not any(r.visualization_type == VisualizationType.LINE for r in recs)


# ============================================================================
# Category Comparison Tests
# ============================================================================


class TestCategoryRecommendation:
    """Test category comparison (bar) recommendations."""

    def test_category_dimension_and_measure_recommends_bar(
        self, viz_engine, category_dimension_low_card, numeric_measure
    ):
        """Category dimension + measure should recommend bar chart."""
        columns = [category_dimension_low_card, numeric_measure]
        recs = viz_engine.recommend(columns, row_count=2, result_id="result_001")

        assert any(r.visualization_type == VisualizationType.BAR for r in recs)
        bar_rec = [r for r in recs if r.visualization_type == VisualizationType.BAR][0]
        assert bar_rec.reason_code == VisualizationRecommendationReason.CATEGORY_COMPARISON

    def test_category_single_row_no_bar(
        self, viz_engine, category_dimension_low_card, numeric_measure
    ):
        """Category dimension with only one row should not recommend bar."""
        columns = [category_dimension_low_card, numeric_measure]
        recs = viz_engine.recommend(columns, row_count=1, result_id="result_001")

        # Single row, should not recommend bar (no comparison)
        assert not any(r.visualization_type == VisualizationType.BAR for r in recs)


# ============================================================================
# Pie Chart Governance Tests
# ============================================================================


class TestPieChartGovernance:
    """Test conservative pie chart governance."""

    def test_pie_eligible_low_cardinality(
        self, viz_engine, category_dimension_low_card, numeric_measure
    ):
        """Low-cardinality category + measure should be pie eligible."""
        is_eligible = viz_engine._is_pie_eligible(
            [category_dimension_low_card], [numeric_measure], row_count=2
        )
        assert is_eligible

    def test_pie_not_eligible_high_cardinality(
        self, viz_engine, category_dimension_high_card, numeric_measure
    ):
        """High-cardinality category should not be pie eligible."""
        is_eligible = viz_engine._is_pie_eligible(
            [category_dimension_high_card], [numeric_measure], row_count=50
        )
        assert not is_eligible  # > MAX_PIE_CARDINALITY

    def test_pie_not_eligible_multiple_dimensions(
        self, viz_engine, category_dimension_low_card, numeric_measure
    ):
        """Multiple categories should not be pie eligible."""
        is_eligible = viz_engine._is_pie_eligible(
            [category_dimension_low_card, category_dimension_low_card],
            [numeric_measure],
            row_count=2,
        )
        assert not is_eligible

    def test_pie_not_eligible_multiple_measures(
        self, viz_engine, category_dimension_low_card, numeric_measure
    ):
        """Multiple measures should not be pie eligible."""
        is_eligible = viz_engine._is_pie_eligible(
            [category_dimension_low_card], [numeric_measure, numeric_measure], row_count=2
        )
        assert not is_eligible

    def test_pie_not_eligible_negative_values(self, viz_engine, category_dimension_low_card):
        """Negative values should make pie ineligible."""
        cat_dim = ColumnInfo(
            identifier="cat",
            name="Category",
            data_type="TEXT",
            role="dimension",
            cardinality=2,
            sample_values=["A", "B"],
        )
        measure = ColumnInfo(
            identifier="val",
            name="Value",
            data_type="DECIMAL",
            role="measure",
            cardinality=2,
            sample_values=["100.00", "-50.00"],  # negative!
        )
        is_eligible = viz_engine._is_pie_eligible([cat_dim], [measure], row_count=2)
        assert not is_eligible

    def test_pie_recommendation_respects_governance(
        self, viz_engine, category_dimension_low_card, numeric_measure
    ):
        """Pie recommendations should respect all governance rules."""
        columns = [category_dimension_low_card, numeric_measure]
        recs = viz_engine.recommend(columns, row_count=2, result_id="result_001")

        pie_recs = [r for r in recs if r.visualization_type == VisualizationType.PIE]
        # Should have pie recommendation for low-card category
        assert len(pie_recs) > 0
        assert pie_recs[0].reason_code == VisualizationRecommendationReason.PART_TO_WHOLE

    def test_pie_blocked_for_high_cardinality(
        self, viz_engine, category_dimension_high_card, numeric_measure
    ):
        """Pie recommendation should be blocked for high cardinality."""
        columns = [category_dimension_high_card, numeric_measure]
        recs = viz_engine.recommend(columns, row_count=50, result_id="result_001")

        pie_recs = [r for r in recs if r.visualization_type == VisualizationType.PIE]
        # Should NOT recommend pie for high cardinality
        assert len(pie_recs) == 0


# ============================================================================
# Table Fallback Tests
# ============================================================================


class TestTableFallback:
    """Test table fallback recommendation."""

    def test_empty_result_recommends_table(self, viz_engine):
        """Empty result should recommend table."""
        recs = viz_engine.recommend([], row_count=0, result_id="result_001")

        assert len(recs) > 0
        assert recs[0].visualization_type == VisualizationType.TABLE
        assert recs[0].reason_code == VisualizationRecommendationReason.TABLE_FALLBACK

    def test_no_matching_pattern_recommends_table(self, viz_engine):
        """Result not matching any pattern should recommend table."""
        # Multiple measures, no dimensions
        measures = [
            ColumnInfo(
                identifier=f"measure_{i}",
                name=f"Measure{i}",
                data_type="DECIMAL",
                role="measure",
                cardinality=1,
            )
            for i in range(3)
        ]
        recs = viz_engine.recommend(measures, row_count=5, result_id="result_001")

        # Should fall back to table
        table_recs = [r for r in recs if r.visualization_type == VisualizationType.TABLE]
        assert len(table_recs) > 0


# ============================================================================
# Full Pipeline Tests
# ============================================================================


class TestFullRecommendationPipeline:
    """Test complete recommendation generation."""

    def test_recommend_for_sales_data(
        self, viz_engine, time_dimension, category_dimension_low_card, numeric_measure
    ):
        """Test recommendations for typical sales dataset."""
        columns = [time_dimension, category_dimension_low_card, numeric_measure]
        recs = viz_engine.recommend(columns, row_count=12, result_id="sales_001")

        assert len(recs) > 0
        # Should recommend line, bar, and table
        types = {r.visualization_type for r in recs}
        assert VisualizationType.LINE in types or VisualizationType.BAR in types

    def test_recommendations_are_deterministic(self, viz_engine, time_dimension, numeric_measure):
        """Recommendations should be deterministic."""
        columns = [time_dimension, numeric_measure]

        recs1 = viz_engine.recommend(columns, row_count=6, result_id="result_001")
        recs2 = viz_engine.recommend(columns, row_count=6, result_id="result_001")

        assert len(recs1) == len(recs2)
        for r1, r2 in zip(recs1, recs2):
            assert r1.visualization_type == r2.visualization_type
            assert r1.reason_code == r2.reason_code

    def test_all_recommendations_have_reason_code(
        self, viz_engine, time_dimension, numeric_measure
    ):
        """All recommendations should have a reason code."""
        columns = [time_dimension, numeric_measure]
        recs = viz_engine.recommend(columns, row_count=6, result_id="result_001")

        assert all(r.reason_code is not None for r in recs)
        # Reason codes should be from enum
        valid_codes = {
            VisualizationRecommendationReason.TIME_SERIES_MEASURE,
            VisualizationRecommendationReason.CATEGORY_COMPARISON,
            VisualizationRecommendationReason.PART_TO_WHOLE,
            VisualizationRecommendationReason.SINGLE_AGGREGATE,
            VisualizationRecommendationReason.GEOGRAPHIC_MEASURE,
            VisualizationRecommendationReason.TABLE_FALLBACK,
            VisualizationRecommendationReason.AMBIGUOUS_SHAPE,
        }
        assert all(r.reason_code in valid_codes for r in recs)

    def test_recommendations_have_confidence(self, viz_engine, numeric_measure):
        """All recommendations should have confidence status."""
        recs = viz_engine.recommend([numeric_measure], row_count=1, result_id="result_001")

        assert all(
            r.confidence in [ConfidenceStatus.SUPPORTED, ConfidenceStatus.PARTIAL] for r in recs
        )


# ============================================================================
# Edge Cases
# ============================================================================


class TestEdgeCases:
    """Test edge cases and error conditions."""

    def test_single_row_dataset(self, viz_engine, numeric_measure):
        """Single row should work and recommend KPI if aggregate."""
        recs = viz_engine.recommend([numeric_measure], row_count=1, result_id="result_001")

        assert len(recs) > 0
        assert any(r.visualization_type == VisualizationType.KPI for r in recs)

    def test_no_columns(self, viz_engine):
        """No columns should recommend table."""
        recs = viz_engine.recommend([], row_count=0, result_id="result_001")

        assert len(recs) > 0
        assert recs[0].visualization_type == VisualizationType.TABLE

    def test_mix_of_dimensions_and_measures(
        self, viz_engine, time_dimension, category_dimension_low_card, numeric_measure
    ):
        """Mixed dimensions and measures should generate appropriate recommendations."""
        columns = [time_dimension, category_dimension_low_card, numeric_measure]
        recs = viz_engine.recommend(columns, row_count=24, result_id="result_001")

        assert len(recs) > 0
        # Should recommend multiple visualization options
        types = {r.visualization_type for r in recs}
        assert len(types) > 1
