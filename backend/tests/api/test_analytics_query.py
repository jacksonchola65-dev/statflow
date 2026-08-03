from __future__ import annotations

import uuid

import pytest
from app.models.data_source import FileFormat, SourceType
from app.models.ingestion import InferredColumnType, IngestionJob, IngestionStatus
from app.repositories.data_source_repository import DataSourceRepository
from app.repositories.dataset_column_repository import DatasetColumnRepository
from app.repositories.dataset_registry_repository import DatasetRegistryRepository
from app.repositories.dataset_row_repository import DatasetRowRepository
from app.repositories.ingestion_job_repository import IngestionJobRepository
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession


async def _make_dataset(
    db_session: AsyncSession, status: IngestionStatus = IngestionStatus.COMPLETED
) -> IngestionJob:
    ds_repo = DataSourceRepository(db_session)
    data_source = await ds_repo.create(name="Analytics Source", is_active=True)
    await db_session.flush()

    reg_repo = DatasetRegistryRepository(db_session)
    registry = await reg_repo.create(
        data_source_id=data_source.id,
        dataset_name="Analytics Dataset",
        source_type=SourceType.OFFICIAL,
        file_format=FileFormat.CSV,
    )
    await db_session.flush()

    job_repo = IngestionJobRepository(db_session)
    job = await job_repo.create(
        dataset_registry_id=registry.id,
        original_filename="analytics.csv",
        file_format=FileFormat.CSV,
        file_size_bytes=128,
        status=status,
    )
    await db_session.flush()

    column_repo = DatasetColumnRepository(db_session)
    await column_repo.create_many(
        [
            {
                "ingestion_job_id": job.id,
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
                "ingestion_job_id": job.id,
                "ordinal_position": 1,
                "original_name": "Population",
                "normalized_name": "population",
                "inferred_type": InferredColumnType.INTEGER,
                "nullable": False,
                "missing_count": 0,
                "unique_count": 2,
                "sample_values": ["100", "200"],
            },
            {
                "ingestion_job_id": job.id,
                "ordinal_position": 2,
                "original_name": "Revenue",
                "normalized_name": "revenue",
                "inferred_type": InferredColumnType.INTEGER,
                "nullable": False,
                "missing_count": 0,
                "unique_count": 2,
                "sample_values": ["10", "20"],
            },
        ]
    )
    row_repo = DatasetRowRepository(db_session)
    await row_repo.create_many(
        [
            {
                "ingestion_job_id": job.id,
                "row_number": 0,
                "values": {"region": "North", "population": 100, "revenue": 10},
            },
            {
                "ingestion_job_id": job.id,
                "row_number": 1,
                "values": {"region": "South", "population": 200, "revenue": 20},
            },
        ]
    )
    await db_session.flush()
    return job


@pytest.mark.asyncio
async def test_post_query_returns_200_and_analytics_result(
    authed_client: AsyncClient, db_session: AsyncSession
) -> None:
    job = await _make_dataset(db_session)
    request = {
        "dataset_reference": {"ingestion_job_id": str(job.id)},
        "dimensions": [{"column_name": "region"}],
        "measures": [{"aggregation": "COUNT", "alias": "row_count"}],
    }

    response = await authed_client.post("/api/v1/analytics/query", json=request)
    assert response.status_code == 200

    payload = response.json()
    assert payload["ingestion_job_id"] == str(job.id)
    assert payload["limit"] == 100
    assert payload["offset"] == 0
    assert payload["has_more"] is False
    assert payload["row_count"] == 2
    assert {column["identifier"] for column in payload["columns"]} == {"region", "row_count"}
    assert {row["region"] for row in payload["rows"]} == {"North", "South"}
    assert all(row["row_count"] == 1 for row in payload["rows"])


@pytest.mark.asyncio
async def test_query_with_unknown_ingestion_job_returns_404(
    authed_client: AsyncClient,
) -> None:
    request = {
        "dataset_reference": {"ingestion_job_id": str(uuid.uuid4())},
        "dimensions": [{"column_name": "region"}],
        "measures": [{"aggregation": "COUNT", "alias": "row_count"}],
    }

    response = await authed_client.post("/api/v1/analytics/query", json=request)
    assert response.status_code == 404
    assert response.json()["detail"] == "Ingestion job not found."


@pytest.mark.asyncio
async def test_query_with_incomplete_ingestion_job_returns_400(
    authed_client: AsyncClient, db_session: AsyncSession
) -> None:
    job = await _make_dataset(db_session, status=IngestionStatus.PENDING)
    request = {
        "dataset_reference": {"ingestion_job_id": str(job.id)},
        "dimensions": [{"column_name": "region"}],
        "measures": [{"aggregation": "COUNT", "alias": "row_count"}],
    }

    response = await authed_client.post("/api/v1/analytics/query", json=request)
    assert response.status_code == 400
    assert response.json()["detail"] == "Ingestion job is not complete."


@pytest.mark.asyncio
async def test_query_invalid_column_returns_400(
    authed_client: AsyncClient, db_session: AsyncSession
) -> None:
    job = await _make_dataset(db_session)
    request = {
        "dataset_reference": {"ingestion_job_id": str(job.id)},
        "dimensions": [{"column_name": "missing"}],
        "measures": [{"aggregation": "COUNT", "alias": "row_count"}],
    }

    response = await authed_client.post("/api/v1/analytics/query", json=request)
    assert response.status_code == 400
    assert "unknown column" in response.json()["detail"]


@pytest.mark.asyncio
async def test_malformed_query_returns_422(authed_client: AsyncClient) -> None:
    request = {"dataset_reference": {"ingestion_job_id": str(uuid.uuid4())}}
    response = await authed_client.post("/api/v1/analytics/query", json=request)
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_unauthenticated_request_returns_401(client: AsyncClient) -> None:
    request = {
        "dataset_reference": {"ingestion_job_id": str(uuid.uuid4())},
        "dimensions": [{"column_name": "region"}],
        "measures": [{"aggregation": "COUNT", "alias": "row_count"}],
    }

    response = await client.post("/api/v1/analytics/query", json=request)
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_query_sorting_and_filters_are_supported(
    authed_client: AsyncClient, db_session: AsyncSession
) -> None:
    job = await _make_dataset(db_session)
    request = {
        "dataset_reference": {"ingestion_job_id": str(job.id)},
        "dimensions": [{"column_name": "region"}],
        "measures": [
            {"aggregation": "SUM", "column_name": "population", "alias": "population_sum"},
        ],
        "filters": [{"column_name": "region", "operator": "EQUALS", "value": "South"}],
        "sorting": [{"target": "region", "direction": "DESCENDING"}],
    }

    response = await authed_client.post("/api/v1/analytics/query", json=request)
    assert response.status_code == 200
    payload = response.json()
    assert payload["row_count"] == 1
    assert payload["rows"][0]["region"] == "South"
    assert payload["rows"][0]["population_sum"] == 200
