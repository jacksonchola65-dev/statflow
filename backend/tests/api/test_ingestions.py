"""
tests/api/test_ingestions.py
===========================

Endpoint tests for the dataset inspection API.

These tests exercise the thin HTTP layer only. The underlying service is mocked
where appropriate to avoid retesting service logic.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import app.api.v1.endpoints.ingestions as ingestions_module
import pytest
from app.core.config import settings
from app.core.security import create_access_token
from app.models.user import UserRole
from app.schemas.ingestion import (
    DatasetColumnResponse,
    DatasetInspectionResponse,
    DatasetRowResponse,
    IngestionJobSummaryResponse,
    PaginationResponse,
)
from app.services.auth_service import AuthService
from app.services.ingestion_inspection_service import (
    IngestionJobNotFoundError,
)
from fastapi import status
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession


def _auth_cookie(user_id: uuid.UUID, role: UserRole) -> dict:
    token = create_access_token(user_id=user_id, role=role, email="test@example.com")
    return {settings.AUTH_COOKIE_NAME: token}


async def _make_user(db_session: AsyncSession, role: UserRole):
    svc = AuthService(db_session)
    user = await svc.create_user(
        email=f"user-{uuid.uuid4().hex[:8]}@example.com",
        password="TestPassword123!",
        full_name="Endpoint Test User",
        role=role,
        is_active=True,
    )
    await db_session.flush()
    return user


@pytest.mark.asyncio
async def test_get_ingestion_inspection_returns_200(
    authed_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
):
    expected = DatasetInspectionResponse(
        job=IngestionJobSummaryResponse(
            id=uuid.uuid4(),
            dataset_registry_id=uuid.uuid4(),
            status="COMPLETED",
            original_filename="test.csv",
            file_format=None,
            row_count=1,
            column_count=1,
            started_at=datetime.now(timezone.utc),
            completed_at=datetime.now(timezone.utc),
            failed_at=None,
            error_message=None,
            created_by_user_id=uuid.uuid4(),
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        ),
        columns=[
            DatasetColumnResponse(
                id=uuid.uuid4(),
                ingestion_job_id=uuid.uuid4(),
                ordinal_position=0,
                original_name="Column 0",
                normalized_name="column_0",
                inferred_type="TEXT",
                nullable=False,
                missing_count=0,
                unique_count=1,
                sample_values=["a"],
                created_at=datetime.now(timezone.utc),
            )
        ],
        rows=[
            DatasetRowResponse(
                id=uuid.uuid4(),
                ingestion_job_id=uuid.uuid4(),
                row_number=0,
                values={"column_0": "a"},
                created_at=datetime.now(timezone.utc),
            )
        ],
        pagination=PaginationResponse(
            page=1,
            page_size=1,
            total_items=1,
            total_pages=1,
            has_next=False,
            has_previous=False,
        ),
    )

    class StubService:
        def __init__(self, session):
            self.session = session

        async def get_inspection(
            self, ingestion_job_id: uuid.UUID, page: int = 1, page_size: int = 50
        ):
            return expected

    monkeypatch.setattr(ingestions_module, "IngestionInspectionService", StubService)

    job_id = uuid.uuid4()
    response = await authed_client.get(f"/api/v1/ingestions/{job_id}?page=1&page_size=1")

    assert response.status_code == status.HTTP_200_OK
    assert response.json() == expected.model_dump(mode="json")


@pytest.mark.asyncio
async def test_get_ingestion_inspection_missing_job_returns_404(
    authed_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
):
    class StubService:
        def __init__(self, session):
            pass

        async def get_inspection(
            self, ingestion_job_id: uuid.UUID, page: int = 1, page_size: int = 50
        ):
            raise IngestionJobNotFoundError("Ingestion job not found.")

    monkeypatch.setattr(ingestions_module, "IngestionInspectionService", StubService)

    response = await authed_client.get(f"/api/v1/ingestions/{uuid.uuid4()}")

    assert response.status_code == status.HTTP_404_NOT_FOUND
    assert "not found" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_get_ingestion_inspection_invalid_uuid_returns_422(authed_client: AsyncClient):
    response = await authed_client.get("/api/v1/ingestions/not-a-uuid")

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    assert response.json()["detail"]


@pytest.mark.asyncio
async def test_get_ingestion_inspection_invalid_page_returns_422(authed_client: AsyncClient):
    response = await authed_client.get(f"/api/v1/ingestions/{uuid.uuid4()}?page=0")

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    assert response.json()["detail"]


@pytest.mark.asyncio
async def test_get_ingestion_inspection_invalid_page_size_returns_422(authed_client: AsyncClient):
    response = await authed_client.get(f"/api/v1/ingestions/{uuid.uuid4()}?page_size=10001")

    assert response.status_code == status.HTTP_422_UNPROCESSABLE_ENTITY
    assert response.json()["detail"]


@pytest.mark.asyncio
async def test_get_ingestion_inspection_page_beyond_total_returns_empty_rows(
    authed_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
):
    expected = DatasetInspectionResponse(
        job=IngestionJobSummaryResponse(
            id=uuid.uuid4(),
            dataset_registry_id=uuid.uuid4(),
            status="COMPLETED",
            original_filename="test.csv",
            file_format=None,
            row_count=1,
            column_count=1,
            started_at=datetime.now(timezone.utc),
            completed_at=datetime.now(timezone.utc),
            failed_at=None,
            error_message=None,
            created_by_user_id=uuid.uuid4(),
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        ),
        columns=[],
        rows=[],
        pagination=PaginationResponse(
            page=2,
            page_size=10,
            total_items=1,
            total_pages=1,
            has_next=False,
            has_previous=True,
        ),
    )

    class StubService:
        def __init__(self, session):
            pass

        async def get_inspection(
            self, ingestion_job_id: uuid.UUID, page: int = 1, page_size: int = 50
        ):
            return expected

    monkeypatch.setattr(ingestions_module, "IngestionInspectionService", StubService)

    response = await authed_client.get(f"/api/v1/ingestions/{uuid.uuid4()}?page=2&page_size=10")

    assert response.status_code == status.HTTP_200_OK
    data = response.json()
    assert data["rows"] == []
    assert data["pagination"]["page"] == 2
    assert data["pagination"]["total_pages"] == 1
    assert data["pagination"]["has_previous"] is True


@pytest.mark.asyncio
async def test_get_ingestion_inspection_unauthorized_returns_401(client: AsyncClient):
    response = await client.get(f"/api/v1/ingestions/{uuid.uuid4()}")

    assert response.status_code == status.HTTP_401_UNAUTHORIZED


@pytest.mark.asyncio
async def test_get_ingestion_inspection_forbidden_returns_403(
    client: AsyncClient, db_session: AsyncSession
):
    user = await _make_user(db_session, role=UserRole.VIEWER)
    response = await client.get(
        f"/api/v1/ingestions/{uuid.uuid4()}",
        cookies=_auth_cookie(user.id, user.role),
    )

    assert response.status_code == status.HTTP_403_FORBIDDEN


@pytest.mark.asyncio
async def test_get_ingestion_inspection_preserves_decimal_strings(
    authed_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
):
    expected = DatasetInspectionResponse(
        job=IngestionJobSummaryResponse(
            id=uuid.uuid4(),
            dataset_registry_id=uuid.uuid4(),
            status="COMPLETED",
            original_filename="test.csv",
            file_format=None,
            row_count=1,
            column_count=1,
            started_at=datetime.now(timezone.utc),
            completed_at=datetime.now(timezone.utc),
            failed_at=None,
            error_message=None,
            created_by_user_id=uuid.uuid4(),
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        ),
        columns=[],
        rows=[
            DatasetRowResponse(
                id=uuid.uuid4(),
                ingestion_job_id=uuid.uuid4(),
                row_number=0,
                values={"column_0": "1.23"},
                created_at=datetime.now(timezone.utc),
            )
        ],
        pagination=PaginationResponse(
            page=1,
            page_size=10,
            total_items=1,
            total_pages=1,
            has_next=False,
            has_previous=False,
        ),
    )

    class StubService:
        def __init__(self, session):
            pass

        async def get_inspection(
            self, ingestion_job_id: uuid.UUID, page: int = 1, page_size: int = 50
        ):
            return expected

    monkeypatch.setattr(ingestions_module, "IngestionInspectionService", StubService)

    response = await authed_client.get(f"/api/v1/ingestions/{uuid.uuid4()}?page=1&page_size=10")

    assert response.status_code == status.HTTP_200_OK
    assert response.json()["rows"][0]["values"]["column_0"] == "1.23"
