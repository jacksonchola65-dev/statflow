from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
from app.api.v1.endpoints.analytics import get_dataset_discovery_service
from app.models.data_source import FileFormat, SourceType
from app.models.ingestion import InferredColumnType, IngestionStatus
from app.repositories.data_source_repository import DataSourceRepository
from app.repositories.dataset_column_repository import DatasetColumnRepository
from app.repositories.dataset_registry_repository import DatasetRegistryRepository
from app.repositories.dataset_row_repository import DatasetRowRepository
from app.repositories.ingestion_job_repository import IngestionJobRepository
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession


async def _make_dataset(
    db_session: AsyncSession,
    *,
    status: IngestionStatus = IngestionStatus.COMPLETED,
    row_count: int = 2,
    column_specs: list[dict] | None = None,
    rows: list[dict] | None = None,
    dataset_name: str = "Analytics Dataset",
) -> uuid.UUID:
    source = await DataSourceRepository(db_session).create(
        name=f"Analytics Source {uuid.uuid4().hex[:8]}", is_active=True
    )
    await db_session.flush()

    registry = await DatasetRegistryRepository(db_session).create(
        data_source_id=source.id,
        dataset_name=f"{dataset_name} {uuid.uuid4().hex[:8]}",
        source_type=SourceType.OFFICIAL,
        file_format=FileFormat.CSV,
    )
    await db_session.flush()

    job = await IngestionJobRepository(db_session).create(
        dataset_registry_id=registry.id,
        original_filename="analytics.csv",
        file_format=FileFormat.CSV,
        file_size_bytes=128,
        status=status,
    )
    await db_session.flush()

    if column_specs is None:
        column_specs = [
            {
                "ordinal_position": 0,
                "original_name": "Region",
                "normalized_name": "region",
                "inferred_type": InferredColumnType.TEXT,
                "nullable": False,
                "missing_count": 0,
                "unique_count": 2,
                "sample_values": ["North", "South"],
            },
            {
                "ordinal_position": 1,
                "original_name": "Population",
                "normalized_name": "population",
                "inferred_type": InferredColumnType.INTEGER,
                "nullable": False,
                "missing_count": 0,
                "unique_count": 2,
                "sample_values": ["100", "200"],
            },
        ]

    for spec in column_specs:
        spec["ingestion_job_id"] = job.id
    await DatasetColumnRepository(db_session).create_many(column_specs)

    if rows is None:
        rows = [
            {"row_number": 0, "values": {"region": "North", "population": 100}},
            {"row_number": 1, "values": {"region": "South", "population": 200}},
        ]

    for row in rows:
        row["ingestion_job_id"] = job.id
    if rows:
        await DatasetRowRepository(db_session).create_many(rows)

    await IngestionJobRepository(db_session).update(
        job.id,
        status=status,
        row_count=row_count,
        column_count=len(column_specs),
        completed_at=datetime.now(timezone.utc) if status == IngestionStatus.COMPLETED else None,
    )
    await db_session.flush()
    return job.id


@pytest.mark.asyncio
async def test_list_analytics_datasets_authenticated(
    authed_client: AsyncClient, db_session: AsyncSession
) -> None:
    await _make_dataset(db_session)

    response = await authed_client.get("/api/v1/analytics/datasets")

    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    assert payload["limit"] == 50
    assert payload["offset"] == 0
    assert payload["has_more"] is False
    assert isinstance(payload["items"], list)


@pytest.mark.asyncio
async def test_list_analytics_datasets_unauthenticated(client: AsyncClient) -> None:
    response = await client.get("/api/v1/analytics/datasets")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_list_pagination_metadata(
    authed_client: AsyncClient, db_session: AsyncSession
) -> None:
    _ = await _make_dataset(
        db_session,
        dataset_name="First Dataset",
        row_count=1,
        rows=[{"row_number": 0, "values": {"region": "A", "population": 1}}],
    )
    _ = await _make_dataset(
        db_session,
        dataset_name="Second Dataset",
        row_count=1,
        rows=[{"row_number": 0, "values": {"region": "B", "population": 2}}],
    )

    response = await authed_client.get("/api/v1/analytics/datasets?limit=1&offset=0")
    assert response.status_code == 200
    payload = response.json()
    assert payload["limit"] == 1
    assert payload["offset"] == 0
    assert payload["has_more"] is True
    assert len(payload["items"]) == 1

    response = await authed_client.get("/api/v1/analytics/datasets?limit=1&offset=1")
    assert response.status_code == 200
    payload = response.json()
    assert payload["has_more"] is False
    assert len(payload["items"]) == 1


@pytest.mark.asyncio
async def test_invalid_limit_and_offset_return_422(authed_client: AsyncClient) -> None:
    response = await authed_client.get("/api/v1/analytics/datasets?limit=0")
    assert response.status_code == 422

    response = await authed_client.get("/api/v1/analytics/datasets?offset=-1")
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_get_analytics_dataset_details_returns_200(
    authed_client: AsyncClient, db_session: AsyncSession
) -> None:
    job_id = await _make_dataset(db_session)
    response = await authed_client.get(f"/api/v1/analytics/datasets/{job_id}")
    assert response.status_code == 200
    payload = response.json()
    assert payload["summary"]["ingestion_job_id"] == str(job_id)
    assert payload["summary"]["dataset_name"].startswith("Analytics Dataset")
    assert payload["analytics_ready"] is True
    assert payload["preview_available"] is True


@pytest.mark.asyncio
async def test_get_analytics_dataset_details_unknown_returns_404(
    authed_client: AsyncClient,
) -> None:
    response = await authed_client.get(f"/api/v1/analytics/datasets/{uuid.uuid4()}")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_get_analytics_dataset_details_incomplete_returns_409(
    authed_client: AsyncClient, db_session: AsyncSession
) -> None:
    job_id = await _make_dataset(db_session, status=IngestionStatus.PENDING)
    response = await authed_client.get(f"/api/v1/analytics/datasets/{job_id}")
    assert response.status_code == 409


@pytest.mark.asyncio
async def test_get_schema_orders_columns(
    authed_client: AsyncClient, db_session: AsyncSession
) -> None:
    job_id = await _make_dataset(
        db_session,
        column_specs=[
            {
                "ordinal_position": 2,
                "original_name": "Third",
                "normalized_name": "third",
                "inferred_type": InferredColumnType.TEXT,
                "nullable": False,
                "missing_count": 0,
                "unique_count": 1,
                "sample_values": ["c"],
            },
            {
                "ordinal_position": 0,
                "original_name": "First",
                "normalized_name": "first",
                "inferred_type": InferredColumnType.TEXT,
                "nullable": False,
                "missing_count": 0,
                "unique_count": 1,
                "sample_values": ["a"],
            },
            {
                "ordinal_position": 1,
                "original_name": "Second",
                "normalized_name": "second",
                "inferred_type": InferredColumnType.TEXT,
                "nullable": False,
                "missing_count": 0,
                "unique_count": 1,
                "sample_values": ["b"],
            },
        ],
        rows=[
            {"row_number": 0, "values": {"first": "a", "second": "b", "third": "c"}},
        ],
        row_count=1,
    )
    response = await authed_client.get(f"/api/v1/analytics/datasets/{job_id}/schema")
    assert response.status_code == 200
    payload = response.json()
    assert [col["identifier"] for col in payload] == ["first", "second", "third"]


@pytest.mark.asyncio
async def test_get_dimensions_returns_valid_identifiers(
    authed_client: AsyncClient, db_session: AsyncSession
) -> None:
    job_id = await _make_dataset(
        db_session,
        column_specs=[
            {
                "ordinal_position": 0,
                "original_name": "Text",
                "normalized_name": "text",
                "inferred_type": InferredColumnType.TEXT,
                "nullable": False,
                "missing_count": 0,
                "unique_count": 1,
                "sample_values": ["a"],
            },
            {
                "ordinal_position": 1,
                "original_name": "Number",
                "normalized_name": "number",
                "inferred_type": InferredColumnType.INTEGER,
                "nullable": False,
                "missing_count": 0,
                "unique_count": 1,
                "sample_values": ["1"],
            },
        ],
        rows=[{"row_number": 0, "values": {"text": "a", "number": 1}}],
        row_count=1,
    )
    response = await authed_client.get(f"/api/v1/analytics/datasets/{job_id}/dimensions")
    assert response.status_code == 200
    payload = response.json()
    assert {item["identifier"] for item in payload} == {"text", "number"}


@pytest.mark.asyncio
async def test_get_measures_returns_supported_aggregations(
    authed_client: AsyncClient, db_session: AsyncSession
) -> None:
    job_id = await _make_dataset(
        db_session,
        column_specs=[
            {
                "ordinal_position": 0,
                "original_name": "Revenue",
                "normalized_name": "revenue",
                "inferred_type": InferredColumnType.INTEGER,
                "nullable": False,
                "missing_count": 0,
                "unique_count": 2,
                "sample_values": ["10", "20"],
            },
        ],
        rows=[{"row_number": 0, "values": {"revenue": 10}}],
        row_count=1,
    )
    response = await authed_client.get(f"/api/v1/analytics/datasets/{job_id}/measures")
    assert response.status_code == 200
    payload = response.json()
    assert payload[0]["identifier"] == "revenue"
    assert payload[0]["supported_aggregations"] == [
        "COUNT",
        "COUNT_DISTINCT",
        "SUM",
        "AVERAGE",
        "MINIMUM",
        "MAXIMUM",
    ]


@pytest.mark.asyncio
async def test_get_preview_default_and_maximum_limit(
    authed_client: AsyncClient, db_session: AsyncSession
) -> None:
    job_id = await _make_dataset(
        db_session,
        rows=[{"row_number": i, "values": {"region": f"R{i}", "population": i}} for i in range(15)],
        row_count=15,
    )
    response = await authed_client.get(f"/api/v1/analytics/datasets/{job_id}/preview")
    assert response.status_code == 200
    payload = response.json()
    assert payload["limit"] == 10
    assert payload["returned_count"] == 10

    response = await authed_client.get(f"/api/v1/analytics/datasets/{job_id}/preview?limit=50")
    assert response.status_code == 200
    payload = response.json()
    assert payload["limit"] == 50
    assert payload["returned_count"] == 15


@pytest.mark.asyncio
async def test_get_preview_empty_dataset_returns_empty_rows(
    authed_client: AsyncClient, db_session: AsyncSession
) -> None:
    job_id = await _make_dataset(
        db_session,
        rows=[],
        row_count=0,
    )
    response = await authed_client.get(f"/api/v1/analytics/datasets/{job_id}/preview")
    assert response.status_code == 200
    payload = response.json()
    assert payload["rows"] == []
    assert payload["returned_count"] == 0


@pytest.mark.asyncio
async def test_get_statistics_returns_persisted_counts(
    authed_client: AsyncClient, db_session: AsyncSession
) -> None:
    job_id = await _make_dataset(db_session)
    response = await authed_client.get(f"/api/v1/analytics/datasets/{job_id}/statistics")
    assert response.status_code == 200
    payload = response.json()
    assert payload["row_count"] == 2
    assert payload["column_count"] == 2
    assert payload["numeric_column_count"] == 1
    assert payload["text_column_count"] == 1
    assert payload["nullable_column_count"] == 0


@pytest.mark.asyncio
async def test_internal_database_fields_absent(
    authed_client: AsyncClient, db_session: AsyncSession
) -> None:
    job_id = await _make_dataset(db_session)
    response = await authed_client.get(f"/api/v1/analytics/datasets/{job_id}")
    assert response.status_code == 200
    body = response.text
    assert "dataset_rows" not in body
    assert "dataset_columns" not in body
    assert "ingestion_jobs" not in body
    assert "dataset_registry" not in body


@pytest.mark.asyncio
async def test_database_errors_are_sanitized(
    authed_client: AsyncClient, db_session: AsyncSession
) -> None:
    app = authed_client._transport.app

    class BrokenService:
        async def list_datasets(self, limit: int = 50, offset: int = 0):
            raise RuntimeError("database connection failed")

    app.dependency_overrides[get_dataset_discovery_service] = lambda: BrokenService()
    response = await authed_client.get("/api/v1/analytics/datasets")
    assert response.status_code == 500
    assert (
        response.json()["detail"] == "An unexpected error occurred while retrieving dataset list."
    )
    assert "database connection failed" not in response.text


@pytest.mark.asyncio
async def test_preview_limit_exceeds_maximum_returns_422(
    authed_client: AsyncClient, db_session: AsyncSession
) -> None:
    job_id = await _make_dataset(db_session)
    response = await authed_client.get(f"/api/v1/analytics/datasets/{job_id}/preview?limit=100")
    assert response.status_code == 422
