"""
services/ingestion_persistence_service.py
===========================================
Ingestion Persistence Orchestrator

Persists an already-validated IngestionProfileResult into the database.

This service does NOT parse files, infer types, normalize headers, or
re-serialize row values. It consumes the approved output of the ingestion
profiling service and orchestrates existing repositories within one
transaction boundary.

Architecture:
  - Orchestrates IngestionJobRepository, DatasetColumnRepository, DatasetRowRepository
  - Maintains one transaction boundary per persist_profile() call
  - Uses bounded batching for rows via DatasetRowRepository.create_many()
  - Rolls back completely if any step fails
  - Returns a typed IngestionPersistenceResult

Status lifecycle (where supported):
  PENDING → COMPLETED (on success)
  PENDING → rolled back (on failure)

Exception hierarchy:
  IngestionPersistenceError — wraps repository/database failures with __cause__
"""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.data_source import DatasetRegistry
from app.models.ingestion import (
    IngestionJob,
    IngestionStatus,
)
from app.repositories.dataset_column_repository import DatasetColumnRepository
from app.repositories.dataset_row_repository import DatasetRowRepository
from app.repositories.ingestion_job_repository import IngestionJobRepository
from app.services.ingestion_profiling_service import IngestionProfileResult


# ---------------------------------------------------------------------------
# Exception
# ---------------------------------------------------------------------------


class IngestionPersistenceError(Exception):
    """Raised when persistence orchestration fails.

    The original exception is always preserved as __cause__ via `raise ... from`.
    The transaction is rolled back before the exception is raised to the caller.
    """


# ---------------------------------------------------------------------------
# Result model
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class IngestionPersistenceResult:
    """Result of a successful persist_profile() call."""

    ingestion_job_id: uuid.UUID
    columns_inserted: int
    rows_inserted: int
    final_status: IngestionStatus


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class IngestionPersistenceService:
    """Orchestrates persistence of validated ingestion profiles.

    Stateless — create a new instance per request or use the module-level
    persist_profile() convenience function.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._job_repo = IngestionJobRepository(session)
        self._column_repo = DatasetColumnRepository(session)
        self._row_repo = DatasetRowRepository(session)

    async def persist_profile(
        self,
        *,
        profile: IngestionProfileResult,
        dataset_registry: DatasetRegistry,
        source_type: str,
        source_reference: Optional[str] = None,
        created_by_user_id: Optional[uuid.UUID] = None,
    ) -> IngestionPersistenceResult:
        """Persist a validated IngestionProfileResult into the database.

        Orchestrates creation of an IngestionJob, DatasetColumn records,
        and DatasetRow records within a single transaction.

        The entire operation is atomic: if any step fails, all changes are
        rolled back and IngestionPersistenceError is raised.

        Parameters
        ----------
        profile:
            An already-validated IngestionProfileResult from the profiling service.
            This is NOT reparsed, re-typed, or re-serialized.

        dataset_registry:
            The DatasetRegistry entity that owns this ingestion job.
            Must already exist in the database.

        source_type:
            String describing the source (e.g., "official_data_upload",
            "scheduled_import", "manual_entry"). Free-form; interpreted by
            the caller or stored for later reference.

        source_reference:
            Optional string reference (e.g., a file URL, import ID, or external
            tracking identifier). Interpreted by the caller.

        created_by_user_id:
            Optional UUID of the user who triggered the ingestion.
            Preserved via SET NULL if the user is later deleted.

        Returns
        -------
        IngestionPersistenceResult
            Contains the created ingestion_job_id, counts of inserted columns
            and rows, and the final_status (COMPLETED).

        Raises
        ------
        IngestionPersistenceError
            If any step fails. The transaction is rolled back before raising.
            The original exception is preserved as __cause__.

        Transaction behaviour:
            - One transaction boundary per call
            - No intermediate commits
            - Rollback occurs automatically on exception (via context manager
              or explicit handling by the service layer)
        """
        try:
            transaction_context = (
                self._session.begin_nested()
                if self._session.in_transaction()
                else self._session.begin()
            )
            async with transaction_context:
                # Step 1: Create IngestionJob
                job = await self._job_repo.create(
                    dataset_registry_id=dataset_registry.id,
                    original_filename=profile.original_filename,
                    file_format=profile.detected_file_format,
                    file_size_bytes=0,  # Not available from profile; set by caller if needed
                    created_by_user_id=created_by_user_id,
                    status=IngestionStatus.PENDING,
                )

                # Step 2: Persist DatasetColumn records
                if profile.columns:
                    column_dicts = [
                        {
                            "ingestion_job_id": job.id,
                            "ordinal_position": col.ordinal_position,
                            "original_name": col.original_name,
                            "normalized_name": col.normalized_name,
                            "inferred_type": col.inferred_type,
                            "nullable": col.nullable,
                            "missing_count": col.missing_count,
                            "unique_count": col.unique_count,
                            "sample_values": col.sample_values if col.sample_values else None,
                        }
                        for col in profile.columns
                    ]
                    columns_inserted = len(
                        await self._column_repo.create_many(column_dicts)
                    )
                else:
                    columns_inserted = 0

                # Step 3: Persist DatasetRow records
                if profile.rows:
                    row_dicts = [
                        {
                            "ingestion_job_id": job.id,
                            "row_number": row.row_number,
                            "values": row.values,
                        }
                        for row in profile.rows
                    ]
                    rows_inserted = await self._row_repo.create_many(row_dicts)
                else:
                    rows_inserted = 0

                # Step 4: Update IngestionJob with final counts and status
                updated_job = await self._job_repo.update(
                    job.id,
                    row_count=profile.row_count,
                    column_count=profile.column_count,
                    status=IngestionStatus.COMPLETED,
                    completed_at=datetime.now(timezone.utc),
                )

                if updated_job is None:
                    raise IngestionPersistenceError(
                        f"Failed to update ingestion job {job.id} after persisting "
                        f"columns and rows. Job may have been deleted."
                    )

                return IngestionPersistenceResult(
                    ingestion_job_id=job.id,
                    columns_inserted=columns_inserted,
                    rows_inserted=rows_inserted,
                    final_status=IngestionStatus.COMPLETED,
                )

        except asyncio.CancelledError:
            await self._session.rollback()
            raise
        except IngestionPersistenceError:
            await self._session.rollback()
            raise
        except Exception as exc:
            await self._session.rollback()
            raise IngestionPersistenceError(
                f"Ingestion persistence failed: {exc}"
            ) from exc


# ---------------------------------------------------------------------------
# Module-level convenience function
# ---------------------------------------------------------------------------


async def persist_profile(
    session: AsyncSession,
    *,
    profile: IngestionProfileResult,
    dataset_registry: DatasetRegistry,
    source_type: str,
    source_reference: Optional[str] = None,
    created_by_user_id: Optional[uuid.UUID] = None,
) -> IngestionPersistenceResult:
    """Convenience function: create a service and persist a profile.

    Equivalent to:
        service = IngestionPersistenceService(session)
        return await service.persist_profile(...)

    See IngestionPersistenceService.persist_profile() for detailed docs.
    """
    service = IngestionPersistenceService(session)
    return await service.persist_profile(
        profile=profile,
        dataset_registry=dataset_registry,
        source_type=source_type,
        source_reference=source_reference,
        created_by_user_id=created_by_user_id,
    )
