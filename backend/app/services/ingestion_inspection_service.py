"""
services/ingestion_inspection_service.py
========================================

Retrieve persisted ingestion inspection data and assemble a complete response
using existing repositories and approved schemas.

This service is intentionally application-layer only: it does not expose HTTP
endpoints and does not manage transactions. It orchestrates repository reads,
constructs pagination metadata, and returns a validated
`DatasetInspectionResponse`.
"""

from __future__ import annotations

import math
import uuid
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.dataset_column_repository import DatasetColumnRepository
from app.repositories.dataset_row_repository import DatasetRowRepository
from app.repositories.ingestion_job_repository import IngestionJobRepository
from app.schemas.ingestion import (
    DatasetInspectionResponse,
    DatasetRowResponse,
    DatasetColumnResponse,
    IngestionJobSummaryResponse,
    PaginationResponse,
)


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class IngestionInspectionError(Exception):
    """Base class for ingestion inspection service errors."""


class IngestionJobNotFoundError(IngestionInspectionError):
    """Raised when no persisted ingestion job exists for the requested ID."""


class InvalidInspectionPaginationError(IngestionInspectionError):
    """Raised when pagination parameters are invalid for inspection retrieval."""


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class IngestionInspectionService:
    """Application service for retrieving persisted ingestion inspection data."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._job_repo = IngestionJobRepository(session)
        self._column_repo = DatasetColumnRepository(session)
        self._row_repo = DatasetRowRepository(session)

    async def get_inspection(
        self,
        ingestion_job_id: uuid.UUID,
        page: int = 1,
        page_size: int = 50,
    ) -> DatasetInspectionResponse:
        """Return the persisted inspection response for a completed ingestion job.

        Parameters
        ----------
        ingestion_job_id:
            UUID of the persisted ingestion job to retrieve.
        page:
            1-indexed page number for row pagination.
        page_size:
            Number of rows to return in the response.

        Returns
        -------
        DatasetInspectionResponse
            Fully assembled response containing job metadata, column profiles,
            paginated rows, and pagination metadata.

        Raises
        ------
        IngestionJobNotFoundError
            When no ingestion job exists for the provided ID.
        """
        if page < 1:
            raise InvalidInspectionPaginationError(
                "Pagination parameter 'page' must be >= 1."
            )
        if page_size < 1 or page_size > 10_000:
            raise InvalidInspectionPaginationError(
                "Pagination parameter 'page_size' must be between 1 and 10_000."
            )

        job = await self._job_repo.get_by_id(ingestion_job_id)
        if job is None:
            raise IngestionJobNotFoundError(
                f"Ingestion job not found: {ingestion_job_id}"
            )

        columns = await self._column_repo.list_by_ingestion_job(ingestion_job_id)
        total_items = await self._row_repo.count_for_job(ingestion_job_id)

        total_pages = 0 if total_items == 0 else math.ceil(total_items / page_size)
        offset = (page - 1) * page_size
        rows = await self._row_repo.list_by_ingestion_job(
            ingestion_job_id,
            offset=offset,
            limit=page_size,
        )

        pagination = PaginationResponse(
            page=page,
            page_size=page_size,
            total_items=total_items,
            total_pages=total_pages,
            has_next=page < total_pages,
            has_previous=page > 1 and total_pages > 0,
        )

        return DatasetInspectionResponse(
            job=IngestionJobSummaryResponse.model_validate(job),
            columns=[DatasetColumnResponse.model_validate(c) for c in columns],
            rows=[DatasetRowResponse.model_validate(r) for r in rows],
            pagination=pagination,
        )


# ---------------------------------------------------------------------------
# Module-level convenience function
# ---------------------------------------------------------------------------


async def get_inspection(
    session: AsyncSession,
    *,
    ingestion_job_id: uuid.UUID,
    page: int = 1,
    page_size: int = 50,
) -> DatasetInspectionResponse:
    """Convenience wrapper for IngestionInspectionService.get_inspection()."""
    service = IngestionInspectionService(session)
    return await service.get_inspection(
        ingestion_job_id=ingestion_job_id,
        page=page,
        page_size=page_size,
    )
