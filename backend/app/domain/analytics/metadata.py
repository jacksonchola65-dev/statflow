from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ingestion import DatasetColumn, IngestionJob, IngestionStatus
from .exceptions import IncompleteIngestionJobError, InvalidIdentifierError, UnknownIngestionJobError


@dataclass(frozen=True)
class ResolvedIdentifier:
    column_name: str
    metadata: DatasetColumn
    source: str


class IngestionMetadataResolver:
    """Resolve analytics identifiers against persisted ingestion metadata."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def resolve_dataset(self, ingestion_job_id) -> IngestionJob:
        result = await self._session.execute(
            select(IngestionJob).where(IngestionJob.id == ingestion_job_id)
        )
        job = result.scalar_one_or_none()
        if job is None:
            raise UnknownIngestionJobError("unknown ingestion_job_id")
        if job.status != IngestionStatus.COMPLETED:
            raise IncompleteIngestionJobError("ingestion job is not complete")
        return job

    async def resolve_column(self, ingestion_job_id, column_name: str) -> ResolvedIdentifier:
        result = await self._session.execute(
            select(DatasetColumn).where(
                DatasetColumn.ingestion_job_id == ingestion_job_id,
                DatasetColumn.normalized_name == column_name,
            )
        )
        column = result.scalar_one_or_none()
        if column is None:
            raise InvalidIdentifierError(f"unknown column: {column_name}")
        return ResolvedIdentifier(column_name=column_name, metadata=column, source="dataset_column")
