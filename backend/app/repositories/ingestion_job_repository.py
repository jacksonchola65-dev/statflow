"""
repositories/ingestion_job_repository.py
=========================================
Data access layer for IngestionJob entities.

Follows the StatFlow repository pattern:
- AsyncSession injected via __init__.
- Never calls commit(), rollback(), or close().
- flush() used after add() so the generated UUID is available to callers.
- No business logic or HTTP exceptions — pure data access.
- Returns ORM model objects, not raw Result objects.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.data_source import FileFormat
from app.models.ingestion import IngestionJob, IngestionStatus


class IngestionJobRepository:
    """Data access layer for IngestionJob entities."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    async def get_by_id(self, job_id: uuid.UUID) -> Optional[IngestionJob]:
        """Return an IngestionJob by primary key, or None if not found."""
        result = await self._session.execute(
            select(IngestionJob).where(IngestionJob.id == job_id)
        )
        return result.scalar_one_or_none()

    async def exists(self, job_id: uuid.UUID) -> bool:
        """Return True if a job with the given ID exists."""
        result = await self._session.execute(
            select(func.count())
            .select_from(IngestionJob)
            .where(IngestionJob.id == job_id)
        )
        return result.scalar_one() > 0

    async def list_by_dataset_registry(
        self,
        dataset_registry_id: uuid.UUID,
        skip: int = 0,
        limit: int = 50,
    ) -> list[IngestionJob]:
        """Return jobs for a dataset registry entry, newest first.

        Ordered by created_at DESC so the most recent job is always first.
        Supports offset pagination via skip/limit.
        """
        result = await self._session.execute(
            select(IngestionJob)
            .where(IngestionJob.dataset_registry_id == dataset_registry_id)
            .order_by(desc(IngestionJob.created_at), desc(IngestionJob.id))
            .offset(skip)
            .limit(limit)
        )
        return list(result.scalars().all())

    async def list_by_status(
        self,
        status: IngestionStatus,
        skip: int = 0,
        limit: int = 50,
    ) -> list[IngestionJob]:
        """Return jobs matching a specific status, newest first."""
        result = await self._session.execute(
            select(IngestionJob)
            .where(IngestionJob.status == status)
            .order_by(desc(IngestionJob.created_at), desc(IngestionJob.id))
            .offset(skip)
            .limit(limit)
        )
        return list(result.scalars().all())

    async def get_latest_for_dataset(
        self, dataset_registry_id: uuid.UUID
    ) -> Optional[IngestionJob]:
        """Return the most recently created job for a dataset registry entry.

        Uses a single query with ORDER BY + LIMIT 1 to avoid fetching all jobs.
        """
        result = await self._session.execute(
            select(IngestionJob)
            .where(IngestionJob.dataset_registry_id == dataset_registry_id)
            .order_by(desc(IngestionJob.created_at), desc(IngestionJob.id))
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def get_active_jobs(self) -> list[IngestionJob]:
        """Return all jobs currently in PENDING or PROCESSING status.

        Active jobs are ordered by started_at ASC so the oldest running job
        is first — useful for monitoring dashboards and cleanup tasks.
        """
        result = await self._session.execute(
            select(IngestionJob)
            .where(
                IngestionJob.status.in_(
                    [IngestionStatus.PENDING, IngestionStatus.PROCESSING]
                )
            )
            .order_by(IngestionJob.started_at.asc().nulls_last(), IngestionJob.id.asc())
        )
        return list(result.scalars().all())

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    async def create(
        self,
        dataset_registry_id: uuid.UUID,
        original_filename: str,
        file_format: FileFormat,
        file_size_bytes: int,
        created_by_user_id: Optional[uuid.UUID] = None,
        stored_filename: Optional[str] = None,
        status: IngestionStatus = IngestionStatus.PENDING,
    ) -> IngestionJob:
        """Create a new IngestionJob row.

        Sets the initial status to PENDING by default. Calls flush() so the
        generated UUID is available to callers immediately.
        """
        job = IngestionJob(
            dataset_registry_id=dataset_registry_id,
            original_filename=original_filename,
            file_format=file_format,
            file_size_bytes=file_size_bytes,
            created_by_user_id=created_by_user_id,
            stored_filename=stored_filename,
            status=status,
        )
        self._session.add(job)
        await self._session.flush()
        return job

    async def update(
        self,
        job_id: uuid.UUID,
        *,
        status: Optional[IngestionStatus] = None,
        row_count: Optional[int] = None,
        column_count: Optional[int] = None,
        started_at: Optional[datetime] = None,
        completed_at: Optional[datetime] = None,
        failed_at: Optional[datetime] = None,
        error_message: Optional[str] = None,
        stored_filename: Optional[str] = None,
    ) -> Optional[IngestionJob]:
        """Apply only the explicitly provided keyword arguments to the job.

        Returns the updated IngestionJob, or None if the job was not found.
        Does NOT commit.
        """
        job = await self.get_by_id(job_id)
        if job is None:
            return None

        if status is not None:
            job.status = status
        if row_count is not None:
            job.row_count = row_count
        if column_count is not None:
            job.column_count = column_count
        if started_at is not None:
            job.started_at = started_at
        if completed_at is not None:
            job.completed_at = completed_at
        if failed_at is not None:
            job.failed_at = failed_at
        if error_message is not None:
            job.error_message = error_message
        if stored_filename is not None:
            job.stored_filename = stored_filename

        return job

    async def delete(self, job_id: uuid.UUID) -> bool:
        """Delete an IngestionJob by ID (cascades to DatasetColumn rows via DB).

        Returns True if the job was found and deleted, False if not found.
        Does NOT commit.
        """
        job = await self.get_by_id(job_id)
        if job is None:
            return False
        await self._session.delete(job)
        return True
