"""
repositories/dataset_column_repository.py
==========================================
Data access layer for DatasetColumn entities.

Follows the StatFlow repository pattern:
- AsyncSession injected via __init__.
- Never calls commit(), rollback(), or close().
- flush() used after add_all() so generated UUIDs are available to callers.
- No business logic or HTTP exceptions — pure data access.
- Returns ORM model objects, not raw Result objects.
"""

from __future__ import annotations

import uuid
from typing import Optional

from sqlalchemy import asc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ingestion import DatasetColumn, InferredColumnType


class DatasetColumnRepository:
    """Data access layer for DatasetColumn entities."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    async def list_by_ingestion_job(
        self, ingestion_job_id: uuid.UUID
    ) -> list[DatasetColumn]:
        """Return all columns for an ingestion job, ordered by ordinal_position ASC.

        ordinal_position is a zero-based integer assigned at creation time that
        records the column's position in the original source file (CSV or XLSX).
        Ordering by this field guarantees the columns are returned in the same
        left-to-right order as they appeared in the uploaded file.
        """
        result = await self._session.execute(
            select(DatasetColumn)
            .where(DatasetColumn.ingestion_job_id == ingestion_job_id)
            .order_by(asc(DatasetColumn.ordinal_position))
        )
        return list(result.scalars().all())

    async def get_by_normalized_name(
        self,
        ingestion_job_id: uuid.UUID,
        normalized_name: str,
    ) -> Optional[DatasetColumn]:
        """Return the column with a specific normalized name within a job, or None."""
        result = await self._session.execute(
            select(DatasetColumn).where(
                DatasetColumn.ingestion_job_id == ingestion_job_id,
                DatasetColumn.normalized_name == normalized_name,
            )
        )
        return result.scalar_one_or_none()

    async def exists(
        self,
        ingestion_job_id: uuid.UUID,
        normalized_name: str,
    ) -> bool:
        """Return True if a column with the given normalized name exists in the job."""
        result = await self._session.execute(
            select(func.count())
            .select_from(DatasetColumn)
            .where(
                DatasetColumn.ingestion_job_id == ingestion_job_id,
                DatasetColumn.normalized_name == normalized_name,
            )
        )
        return result.scalar_one() > 0

    async def count_for_job(self, ingestion_job_id: uuid.UUID) -> int:
        """Return the total number of columns recorded for a job."""
        result = await self._session.execute(
            select(func.count())
            .select_from(DatasetColumn)
            .where(DatasetColumn.ingestion_job_id == ingestion_job_id)
        )
        return result.scalar_one()

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    async def create_many(
        self, columns: list[dict]
    ) -> list[DatasetColumn]:
        """Bulk-insert DatasetColumn records in a single add_all + flush call.

        Each dict in *columns* must contain:
          - ingestion_job_id, original_name, normalized_name, inferred_type,
            nullable, missing_count, unique_count, ordinal_position (required)
          - sample_values (optional)

        ordinal_position must be zero-based and unique within the job.
        The service layer is responsible for assigning contiguous positions.

        Returns the list of created DatasetColumn ORM objects with their
        generated IDs populated via flush().
        """
        objs = [DatasetColumn(**col) for col in columns]
        self._session.add_all(objs)
        await self._session.flush()
        return objs

    async def delete_by_ingestion_job(self, ingestion_job_id: uuid.UUID) -> int:
        """Delete all DatasetColumn rows belonging to an ingestion job.

        Returns the count of deleted rows. This is provided for cases where
        the service layer needs to replace column data without deleting the
        parent job. In normal usage, the ON DELETE CASCADE on the FK handles
        deletion automatically when the IngestionJob is deleted.
        """
        # Fetch and delete row-by-row so SQLAlchemy can track the deletions
        # in its identity map and fire any configured ORM events.
        # For bulk volumes use session.execute(delete(...)) instead — but for
        # this MVP the column count per job is bounded (max 500 by config).
        result = await self._session.execute(
            select(DatasetColumn).where(
                DatasetColumn.ingestion_job_id == ingestion_job_id
            )
        )
        rows = list(result.scalars().all())
        for row in rows:
            await self._session.delete(row)
        return len(rows)
