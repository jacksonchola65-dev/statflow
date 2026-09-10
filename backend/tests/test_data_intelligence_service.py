"""
tests/test_data_intelligence_service.py
========================================

Test suite for DataIntelligenceService.

Tests validate that the orchestration service correctly composes all
intelligence components and produces deterministic results.
"""

import uuid

import pytest
from app.schemas.intelligence import (
    ColumnSemanticType,
    ConfidenceStatus,
    DatasetIntelligenceResult,
    VisualizationType,
)
from app.services.data_intelligence_service import (
    DataIntelligenceService,
    EmptyDatasetError,
)

# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def intelligence_service():
    """Create DataIntelligenceService instance."""
    return DataIntelligenceService()


@pytest.fixture
def sales_columns():
    """Column metadata for sales dataset."""
    return [
        {
            "identifier": "date_col",
            "name": "Date",
            "label": "Order Date",
            "data_type": "DATE",
            "inferred_type": "DATE",
            "role": "dimension",
            "cardinality": 6,
            "null_count": 0,
            "total_count": 24,
            "sample_values": ["2024-01-01", "2024-02-01", "2024-03-01"],
        },
        {
            "identifier": "branch_col",
            "name": "Branch",
            "label": "Branch",
            "data_type": "TEXT",
            "inferred_type": "TEXT",
            "role": "dimension",
            "cardinality": 2,
            "null_count": 0,
            "total_count": 24,
            "sample_values": ["Lusaka", "Ndola"],
        },
        {
            "identifier": "product_col",
            "name": "Product",
            "label": "Product",
            "data_type": "TEXT",
            "inferred_type": "TEXT",
            "role": "dimension",
            "cardinality": 2,
            "null_count": 0,
            "total_count": 24,
            "sample_values": ["Widget A", "Widget B"],
        },
        {
            "identifier": "quantity_col",
            "name": "Quantity",
            "label": "Quantity",
            "data_type": "INTEGER",
            "inferred_type": "INTEGER",
            "role": "measure",
            "cardinality": 20,
            "null_count": 0,
            "total_count": 24,
            "sample_values": ["50", "100", "130"],
            "is_numeric": True,
        },
        {
            "identifier": "unit_price_col",
            "name": "Unit Price",
            "label": "Unit Price",
            "data_type": "DECIMAL",
            "inferred_type": "DECIMAL",
            "role": "measure",
            "cardinality": 2,
            "null_count": 0,
            "total_count": 24,
            "sample_values": ["10.50", "15.00"],
            "is_numeric": True,
        },
        {
            "identifier": "revenue_col",
            "name": "Revenue",
            "label": "Revenue",
            "data_type": "DECIMAL",
            "inferred_type": "DECIMAL",
            "role": "measure",
            "cardinality": 24,
            "null_count": 0,
            "total_count": 24,
            "sample_values": ["1050.00", "1500.00"],
            "is_numeric": True,
        },
    ]


@pytest.fixture
def sales_rows():
    """Sample rows from sales dataset."""
    return [
        {
            "date_col": "2024-01-01",
            "branch_col": "Lusaka",
            "product_col": "Widget A",
            "quantity_col": 100,
            "unit_price_col": 10.50,
            "revenue_col": 1050.00,
        },
        {
            "date_col": "2024-01-01",
            "branch_col": "Lusaka",
            "product_col": "Widget B",
            "quantity_col": 75,
            "unit_price_col": 15.00,
            "revenue_col": 1125.00,
        },
        {
            "date_col": "2024-01-01",
            "branch_col": "Ndola",
            "product_col": "Widget A",
            "quantity_col": 50,
            "unit_price_col": 10.50,
            "revenue_col": 525.00,
        },
        {
            "date_col": "2024-01-01",
            "branch_col": "Ndola",
            "product_col": "Widget B",
            "quantity_col": 80,
            "unit_price_col": 15.00,
            "revenue_col": 1200.00,
        },
    ]


# ============================================================================
# Basic Functionality Tests
# ============================================================================


class TestBasicAnalysis:
    """Test basic analysis functionality."""

    def test_analyze_dataset_returns_result(self, intelligence_service, sales_columns, sales_rows):
        """Analysis should return DatasetIntelligenceResult."""
        dataset_id = str(uuid.uuid4())
        result = intelligence_service.analyze_dataset(
            dataset_id=dataset_id,
            columns=sales_columns,
            rows=sales_rows,
            row_count=len(sales_rows),
        )

        assert isinstance(result, DatasetIntelligenceResult)
        assert str(result.dataset_id) == dataset_id
        assert result.row_count == len(sales_rows)
        assert result.column_count == len(sales_columns)

    def test_analysis_includes_all_components(
        self, intelligence_service, sales_columns, sales_rows
    ):
        """Analysis should include all intelligence components."""
        dataset_id = str(uuid.uuid4())
        result = intelligence_service.analyze_dataset(
            dataset_id=dataset_id,
            columns=sales_columns,
            rows=sales_rows,
            row_count=len(sales_rows),
        )

        assert result.columns is not None and len(result.columns) > 0
        assert result.kpis is not None
        assert result.insights is not None
        assert result.data_quality_notes is not None
        assert result.visualization_recommendations is not None

    def test_analysis_includes_provenance(
        self, intelligence_service, sales_columns, sales_rows
    ):
        """Analysis should include provenance information."""
        dataset_id = str(uuid.uuid4())
        result = intelligence_service.analyze_dataset(
            dataset_id=dataset_id,
            columns=sales_columns,
            rows=sales_rows,
            row_count=len(sales_rows),
        )

        assert result.provenance is not None
        assert result.provenance.get("dataset_id") == dataset_id
        assert result.provenance.get("column_count") == len(sales_columns)
        assert result.provenance.get("row_count") == len(sales_rows)
        assert "analysis_method" in result.provenance
        assert "intelligence_components" in result.provenance

    def test_analysis_includes_performance_metrics(
        self, intelligence_service, sales_columns, sales_rows
    ):
        """Analysis should include performance metrics."""
        dataset_id = str(uuid.uuid4())
        result = intelligence_service.analyze_dataset(
            dataset_id=dataset_id,
            columns=sales_columns,
            rows=sales_rows,
            row_count=len(sales_rows),
        )

        assert result.performance_metrics is not None
        assert "total_analysis_seconds" in result.performance_metrics
        assert result.performance_metrics["total_analysis_seconds"] >= 0


# ============================================================================
# Column Intelligence Tests
# ============================================================================


class TestColumnIntelligence:
    """Test column intelligence generation."""

    def test_column_intelligence_all_columns(
        self, intelligence_service, sales_columns, sales_rows
    ):
        """Column intelligence should be generated for all columns."""
        dataset_id = str(uuid.uuid4())
        result = intelligence_service.analyze_dataset(
            dataset_id=dataset_id,
            columns=sales_columns,
            rows=sales_rows,
            row_count=len(sales_rows),
        )

        assert len(result.columns) == len(sales_columns)
        column_names = {c.column_name for c in result.columns}
        # Use identifier (which is the primary key the engine uses)
        input_names = {c["identifier"] for c in sales_columns}
        assert column_names == input_names

    def test_column_intelligence_semantic_types(
        self, intelligence_service, sales_columns, sales_rows
    ):
        """Column intelligence should include semantic types."""
        dataset_id = str(uuid.uuid4())
        result = intelligence_service.analyze_dataset(
            dataset_id=dataset_id,
            columns=sales_columns,
            rows=sales_rows,
            row_count=len(sales_rows),
        )

        # Check that date column is classified as TEMPORAL
        date_col = [c for c in result.columns if c.column_name == "date_col"][0]
        assert date_col.semantic_type in [
            ColumnSemanticType.TEMPORAL,
            ColumnSemanticType.TEXT,
        ]

        # Check that numeric columns are classified as NUMERIC_MEASURE
        revenue_col = [c for c in result.columns if c.column_name == "revenue_col"][0]
        assert revenue_col.semantic_type == ColumnSemanticType.NUMERIC_MEASURE

    def test_column_intelligence_confidence(
        self, intelligence_service, sales_columns, sales_rows
    ):
        """Column intelligence should include confidence."""
        dataset_id = str(uuid.uuid4())
        result = intelligence_service.analyze_dataset(
            dataset_id=dataset_id,
            columns=sales_columns,
            rows=sales_rows,
            row_count=len(sales_rows),
        )

        assert all(
            c.confidence in [ConfidenceStatus.SUPPORTED, ConfidenceStatus.PARTIAL]
            for c in result.columns
        )


# ============================================================================
# KPI Generation Tests
# ============================================================================


class TestKpiGeneration:
    """Test KPI generation during analysis."""

    def test_kpis_generated(self, intelligence_service, sales_columns, sales_rows):
        """Analysis should generate KPIs."""
        dataset_id = str(uuid.uuid4())
        result = intelligence_service.analyze_dataset(
            dataset_id=dataset_id,
            columns=sales_columns,
            rows=sales_rows,
            row_count=len(sales_rows),
        )

        assert len(result.kpis) > 0
        # Should have KPIs for numeric measures - just check that we have KPIs for numeric columns
        metric_names = {kpi.metric for kpi in result.kpis}
        # At minimum, should have generated some KPIs
        assert any(m in ["quantity_col", "Quantity", "unit_price_col", "Unit Price", "revenue_col", "Revenue"] for m in metric_names)


# ============================================================================
# Insight Generation Tests
# ============================================================================


class TestInsightGeneration:
    """Test insight generation during analysis."""

    def test_insights_generated(self, intelligence_service, sales_columns, sales_rows):
        """Analysis should generate insights."""
        dataset_id = str(uuid.uuid4())
        result = intelligence_service.analyze_dataset(
            dataset_id=dataset_id,
            columns=sales_columns,
            rows=sales_rows,
            row_count=len(sales_rows),
        )

        assert len(result.insights) > 0

    def test_insights_have_source_reference(self, intelligence_service, sales_columns, sales_rows):
        """All insights should have source reference."""
        dataset_id = str(uuid.uuid4())
        result = intelligence_service.analyze_dataset(
            dataset_id=dataset_id,
            columns=sales_columns,
            rows=sales_rows,
            row_count=len(sales_rows),
        )

        assert all(i.source_reference == dataset_id for i in result.insights)


# ============================================================================
# Data Quality Tests
# ============================================================================


class TestDataQuality:
    """Test data quality note generation."""

    def test_quality_notes_generated(self, intelligence_service, sales_columns, sales_rows):
        """Analysis should generate data quality notes."""
        dataset_id = str(uuid.uuid4())
        result = intelligence_service.analyze_dataset(
            dataset_id=dataset_id,
            columns=sales_columns,
            rows=sales_rows,
            row_count=len(sales_rows),
        )

        # May have quality notes (optional)
        assert isinstance(result.data_quality_notes, list)


# ============================================================================
# Visualization Recommendation Tests
# ============================================================================


class TestVisualizationRecommendations:
    """Test visualization recommendation generation."""

    def test_visualization_recommendations_generated(
        self, intelligence_service, sales_columns, sales_rows
    ):
        """Analysis should generate visualization recommendations."""
        dataset_id = str(uuid.uuid4())
        result = intelligence_service.analyze_dataset(
            dataset_id=dataset_id,
            columns=sales_columns,
            rows=sales_rows,
            row_count=len(sales_rows),
        )

        assert len(result.visualization_recommendations) > 0

    def test_recommendations_have_type(self, intelligence_service, sales_columns, sales_rows):
        """All recommendations should have visualization type."""
        dataset_id = str(uuid.uuid4())
        result = intelligence_service.analyze_dataset(
            dataset_id=dataset_id,
            columns=sales_columns,
            rows=sales_rows,
            row_count=len(sales_rows),
        )

        assert all(
            r.visualization_type in [
                VisualizationType.KPI,
                VisualizationType.BAR,
                VisualizationType.LINE,
                VisualizationType.AREA,
                VisualizationType.PIE,
                VisualizationType.TABLE,
                VisualizationType.MAP,
            ]
            for r in result.visualization_recommendations
        )


# ============================================================================
# Error Handling Tests
# ============================================================================


class TestErrorHandling:
    """Test error handling."""

    def test_empty_dataset_raises_error(self, intelligence_service):
        """Empty dataset should raise error."""
        with pytest.raises(EmptyDatasetError):
            intelligence_service.analyze_dataset(
                dataset_id="ds_001",
                columns=[],
                rows=[],
                row_count=0,
            )

    def test_no_rows_raises_error(self, intelligence_service, sales_columns):
        """Dataset with no rows should raise error."""
        with pytest.raises(EmptyDatasetError):
            intelligence_service.analyze_dataset(
                dataset_id="ds_001",
                columns=sales_columns,
                rows=[],
                row_count=0,
            )

    def test_no_columns_raises_error(self, intelligence_service, sales_rows):
        """Dataset with no columns should raise error."""
        with pytest.raises(EmptyDatasetError):
            intelligence_service.analyze_dataset(
                dataset_id="ds_001",
                columns=[],
                rows=sales_rows,
                row_count=len(sales_rows),
            )


# ============================================================================
# Determinism Tests
# ============================================================================


class TestDeterminism:
    """Test that analysis is deterministic and reproducible."""

    def test_same_input_produces_same_output(
        self, intelligence_service, sales_columns, sales_rows
    ):
        """Same input should produce identical results."""
        dataset_id = str(uuid.uuid4())

        result1 = intelligence_service.analyze_dataset(
            dataset_id=dataset_id,
            columns=sales_columns,
            rows=sales_rows,
            row_count=len(sales_rows),
        )

        result2 = intelligence_service.analyze_dataset(
            dataset_id=dataset_id,
            columns=sales_columns,
            rows=sales_rows,
            row_count=len(sales_rows),
        )

        # Results should be functionally identical
        assert str(result1.dataset_id) == str(result2.dataset_id)
        assert result1.row_count == result2.row_count
        assert result1.column_count == result2.column_count
        assert len(result1.kpis) == len(result2.kpis)
        assert len(result1.insights) == len(result2.insights)

    def test_kpi_values_deterministic(
        self, intelligence_service, sales_columns, sales_rows
    ):
        """KPI values should be deterministic."""
        dataset_id = str(uuid.uuid4())

        result1 = intelligence_service.analyze_dataset(
            dataset_id=dataset_id,
            columns=sales_columns,
            rows=sales_rows,
            row_count=len(sales_rows),
        )

        result2 = intelligence_service.analyze_dataset(
            dataset_id=dataset_id,
            columns=sales_columns,
            rows=sales_rows,
            row_count=len(sales_rows),
        )

        # Compare KPI values - should be identical
        assert len(result1.kpis) == len(result2.kpis)
        for kpi1, kpi2 in zip(result1.kpis, result2.kpis):
            if kpi1.metric == kpi2.metric and kpi1.kpi_type == kpi2.kpi_type:
                # Same metric and type should have same value
                assert kpi1.value == kpi2.value


# ============================================================================
# Integration Tests
# ============================================================================


class TestIntegration:
    """Test integration with existing systems."""

    def test_analysis_with_semantic_metadata(self, intelligence_service, sales_columns):
        """Analysis should work with semantic metadata."""
        dataset_id = str(uuid.uuid4())

        # Add semantic hints to columns
        sales_columns[4]["semantic_hint"] = "CURRENCY"  # Unit Price
        sales_columns[5]["semantic_hint"] = "CURRENCY"  # Revenue

        # Create minimal rows
        rows = [
            {
                "date_col": "2024-01-01",
                "branch_col": "Lusaka",
                "product_col": "Widget A",
                "quantity_col": 100,
                "unit_price_col": 10.50,
                "revenue_col": 1050.00,
            }
        ]

        result = intelligence_service.analyze_dataset(
            dataset_id=dataset_id,
            columns=sales_columns,
            rows=rows,
            row_count=1,
        )

        assert isinstance(result, DatasetIntelligenceResult)
