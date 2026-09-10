from __future__ import annotations

import csv
import io
import uuid
from dataclasses import dataclass

import pytest
from app.domain.analytics.discovery import DatasetDiscoveryRepository, DatasetDiscoveryService
from app.domain.analytics.planner import AnalyticsQueryPlanner
from app.domain.analytics.repository import AnalyticsRepository
from app.domain.analytics.service import AnalyticsService
from app.models.data_source import SourceType
from app.models.user import UserRole
from app.services.official_import_service import (
    ImportData,
    ImportSource,
    OfficialDataImporter,
    OfficialImportService,
)
from app.services.stored_dataset_intelligence_service import StoredDatasetIntelligenceService
from app.tools import ToolExecutionContext, ToolStatus, build_tool_registry
from httpx import AsyncClient

SALES_ROWS = [
    {"Date": "2025-01-15", "Branch": "North", "Product": "A", "Quantity": "2", "Unit Price": "10", "Revenue": "20"},
    {"Date": "2025-01-20", "Branch": "South", "Product": "B", "Quantity": "5", "Unit Price": "20", "Revenue": "100"},
    {"Date": "2025-02-10", "Branch": "North", "Product": "B", "Quantity": "3", "Unit Price": "20", "Revenue": "60"},
    {"Date": "2025-02-22", "Branch": "South", "Product": "A", "Quantity": "4", "Unit Price": "10", "Revenue": "40"},
    {"Date": "2025-03-05", "Branch": "North", "Product": "A", "Quantity": "6", "Unit Price": "10", "Revenue": "60"},
    {"Date": "2025-03-18", "Branch": "South", "Product": "B", "Quantity": "2", "Unit Price": "20", "Revenue": "40"},
]


def _sales_csv() -> bytes:
    stream = io.StringIO()
    writer = csv.DictWriter(stream, fieldnames=list(SALES_ROWS[0]))
    writer.writeheader()
    writer.writerows(SALES_ROWS)
    return stream.getvalue().encode()


@dataclass
class FixtureImporter(OfficialDataImporter):
    content: bytes

    async def import_data(self) -> ImportData:
        return ImportData(
            source=ImportSource.OTHER,
            original_filename="phase-9-2b-sales.csv",
            content=self.content,
            source_reference="local-test-fixture",
        )


async def _make_registry(db_session, name: str):
    from app.repositories.data_source_repository import DataSourceRepository
    from app.repositories.dataset_registry_repository import DatasetRegistryRepository

    source = await DataSourceRepository(db_session).create(
        name=f"Phase 9.2B source {uuid.uuid4().hex[:8]}", is_active=True
    )
    await db_session.flush()
    registry = await DatasetRegistryRepository(db_session).create(
        data_source_id=source.id,
        dataset_name=name,
        source_type=SourceType.INTERNAL,
    )
    await db_session.flush()
    return registry


@pytest.mark.asyncio
async def test_sales_fixture_uses_real_import_storage_and_intelligence_endpoint(
    authed_client: AsyncClient, db_session
):
    name = f"Phase 9.2B Sales {uuid.uuid4().hex[:8]}"
    registry = await _make_registry(db_session, name)
    imported = await OfficialImportService(db_session).import_data(
        FixtureImporter(_sales_csv()), registry
    )

    response = await authed_client.get(
        f"/api/v1/analytics/datasets/{imported.ingestion_job_id}/intelligence"
    )
    assert response.status_code == 200, response.text
    body = response.json()

    expected_revenue = [float(row["Revenue"]) for row in SALES_ROWS]
    assert body["dataset"]["name"] == name
    assert body["dataset"]["row_count"] == len(SALES_ROWS)
    assert body["dataset"]["column_count"] == 6
    assert body["analysis_scope"] == "FULL_DATASET"
    assert body["sample_size"] == len(SALES_ROWS)
    assert body["coverage_ratio"] == 1.0

    kpis = {item["kpi_type"]: item["value"] for item in body["kpis"] if item["metric"] == "revenue"}
    assert kpis["count"] == len(expected_revenue)
    assert kpis["total"] == sum(expected_revenue)
    assert kpis["average"] == sum(expected_revenue) / len(expected_revenue)
    assert kpis["minimum"] == min(expected_revenue)
    assert kpis["maximum"] == max(expected_revenue)

    artifact_types = {item["type"] for item in body["visualizations"]}
    assert "map" not in artifact_types
    assert "bar" in artifact_types
    assert "line" in artifact_types
    assert all(item["analysis_scope"] in {"FULL_DATASET", "PREVIEW"} for item in body["visualizations"])

    insight_types = {item["insight_type"] for item in body["insights"]}
    assert "highest_category" in insight_types
    assert "lowest_category" in insight_types
    assert "highest_period" in insight_types
    assert "lowest_period" in insight_types
    assert body["provenance"]["aggregation_authority"] == "AnalyticsRepository"


@pytest.mark.asyncio
async def test_sales_fixture_executes_through_internal_tool_registry(authed_client, db_session):
    name = f"Phase 9.3 Sales {uuid.uuid4().hex[:8]}"
    registry = await _make_registry(db_session, name)
    imported = await OfficialImportService(db_session).import_data(FixtureImporter(_sales_csv()), registry)
    discovery = DatasetDiscoveryService(DatasetDiscoveryRepository(db_session))
    analytics = AnalyticsService(AnalyticsQueryPlanner(db_session), AnalyticsRepository(db_session))
    tools = build_tool_registry(
        discovery=discovery,
        intelligence=StoredDatasetIntelligenceService(discovery, analytics),
        analytics=analytics,
        db=db_session,
    )
    principal = await authed_client._transport.app.dependency_overrides[
        __import__("app.core.dependencies", fromlist=["get_current_user"]).get_current_user
    ]()
    context = ToolExecutionContext(
        user_id=principal.id,
        role=UserRole.ADMIN,
        request_id="phase-9-3-sales",
    )

    grouped = await tools.execute(
        "run_dataset_analysis",
        {"dataset_id": str(imported.ingestion_job_id), "measure": "revenue", "dimension": "branch", "aggregation": "SUM"},
        context,
    )
    period_average = await tools.execute(
        "run_dataset_analysis",
        {"dataset_id": str(imported.ingestion_job_id), "measure": "revenue", "dimension": "date", "aggregation": "AVERAGE"},
        context,
    )
    product_quantity = await tools.execute(
        "run_dataset_analysis",
        {"dataset_id": str(imported.ingestion_job_id), "measure": "quantity", "dimension": "product", "aggregation": "SUM"},
        context,
    )
    row_count = await tools.execute(
        "run_dataset_analysis",
        {"dataset_id": str(imported.ingestion_job_id), "aggregation": "COUNT"},
        context,
    )
    intelligence = await tools.execute(
        "analyze_dataset", {"dataset_id": str(imported.ingestion_job_id)}, context
    )

    assert grouped.status is ToolStatus.SUCCESS
    assert {row["branch"]: row["value"] for row in grouped.data["rows"]} == {"North": 140, "South": 180}
    assert period_average.status is ToolStatus.SUCCESS
    assert {row["date"]: float(row["value"]) for row in period_average.data["rows"]} == {
        "2025-01-15": 20, "2025-01-20": 100, "2025-02-10": 60,
        "2025-02-22": 40, "2025-03-05": 60, "2025-03-18": 40,
    }
    assert product_quantity.status is ToolStatus.SUCCESS
    assert {row["product"]: row["value"] for row in product_quantity.data["rows"]} == {"A": 12, "B": 10}
    assert row_count.status is ToolStatus.SUCCESS
    assert row_count.data["rows"] == [{"value": 6}]
    assert intelligence.status is ToolStatus.SUCCESS
    assert intelligence.data["analysis_scope"] == "FULL_DATASET"
    assert "map" not in {artifact["type"] for artifact in intelligence.data["visualizations"]}
