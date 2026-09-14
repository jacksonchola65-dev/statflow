from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
from app.domain.analytics.contracts import (
    AnalyticsResult,
    AnalyticsResultColumn,
    AnalyticsResultRole,
)
from app.domain.analytics.dependencies import get_stored_dataset_intelligence_service
from app.models.ingestion import InferredColumnType, IngestionStatus
from app.schemas.intelligence import DatasetIntelligenceResponse
from app.services.stored_dataset_intelligence_service import StoredDatasetIntelligenceService
from httpx import ASGITransport, AsyncClient


class FakeRepository:
    def __init__(self, rows, columns):
        self.rows = rows
        self.columns = columns

    async def list_columns(self, _dataset_id):
        return self.columns

    async def preview_rows(self, _dataset_id, limit):
        return self.rows[:limit]


class FakeDiscovery:
    def __init__(self, dataset_id, rows, columns):
        self._repository = FakeRepository(rows, columns)
        self._summary = SimpleNamespace(
            ingestion_job_id=dataset_id,
            dataset_name="Large sales",
            row_count=len(rows),
            column_count=len(columns),
            completed_at=datetime.now(timezone.utc),
            created_at=datetime.now(timezone.utc),
            status=IngestionStatus.COMPLETED,
        )

    async def get_dataset_details(self, _dataset_id):
        return SimpleNamespace(summary=self._summary)


class FakeAnalytics:
    async def execute(self, query):
        aliases = [measure.alias for measure in query.measures]
        values = {
            "total": 600000.0,
            "count": 6000,
            "average": 100.0,
            "minimum": 1.0,
            "maximum": 250.0,
            "distinct": 6000,
        }
        row = {alias: values[alias] for alias in aliases}
        return AnalyticsResult(
            ingestion_job_id=query.dataset_reference.ingestion_job_id,
            columns=[
                AnalyticsResultColumn(
                    identifier=alias,
                    label=alias,
                    role=AnalyticsResultRole.MEASURE,
                    aggregation=measure.aggregation,
                )
                for alias, measure in zip(aliases, query.measures)
            ],
            rows=[row],
            row_count=1,
            limit=query.limit,
            offset=0,
            has_more=False,
        )


def _column():
    return SimpleNamespace(
        normalized_name="revenue",
        original_name="Revenue",
        inferred_type=InferredColumnType.DECIMAL,
        unique_count=6000,
        missing_count=0,
        sample_values=["1", "250"],
    )


@pytest.mark.asyncio
async def test_large_dataset_uses_bounded_sample_and_exact_kpis():
    dataset_id = uuid4()
    rows = [SimpleNamespace(values={"revenue": float(index + 1)}) for index in range(6000)]
    service = StoredDatasetIntelligenceService(
        FakeDiscovery(dataset_id, rows, [_column()]), FakeAnalytics()
    )

    result = await service.analyze(dataset_id)

    assert isinstance(result, DatasetIntelligenceResponse)
    assert result.sample_size == 5000
    assert result.total_rows == 6000
    assert result.coverage_ratio == pytest.approx(5 / 6)
    assert {k.analysis_scope for k in result.kpis} == {"FULL_DATASET"}
    assert next(k for k in result.kpis if k.kpi_type == "total").value == 600000
    assert all(artifact.analysis_scope != "SAMPLE" for artifact in result.visualizations)


@pytest.mark.asyncio
async def test_anonymous_intelligence_request_is_rejected():
    from app.main import create_app

    app = create_app()
    app.dependency_overrides[get_stored_dataset_intelligence_service] = lambda: None
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        response = await client.get(f"/api/v1/analytics/datasets/{uuid4()}/intelligence")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_authenticated_intelligence_request_returns_scope_metadata():
    from app.core.dependencies import get_current_user
    from app.main import create_app

    dataset_id = uuid4()
    expected = DatasetIntelligenceResponse(
        dataset={"id": dataset_id, "name": "Sales", "row_count": 1, "column_count": 1},
        analysis_scope="FULL_DATASET",
        sample_size=1,
        total_rows=1,
        coverage_ratio=1.0,
    )
    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(id=uuid4(), role="ADMIN")
    app.dependency_overrides[get_stored_dataset_intelligence_service] = lambda: SimpleNamespace(
        analyze=lambda _dataset_id: _async_value(expected)
    )
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        response = await client.get(f"/api/v1/analytics/datasets/{dataset_id}/intelligence")
    assert response.status_code == 200
    assert response.json()["analysis_scope"] == "FULL_DATASET"
    assert response.json()["sample_size"] == 1


async def _async_value(value):
    return value


@pytest.mark.asyncio
async def test_invalid_dataset_identifier_is_safe_failure(client):
    response = await client.get("/api/v1/analytics/datasets/not-a-uuid/intelligence")
    assert response.status_code == 401
