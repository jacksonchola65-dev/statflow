"""
repositories/dataset_row_repository.py
=======================================
Data access layer for DatasetRow entities.

Follows the StatFlow repository pattern:
- AsyncSession injected via __init__.
- Never calls commit(), rollback(), close(), or expunge_all().
- No business validation — only persistence concerns.
- Returns ORM objects for point queries; returns int for bulk writes.
- No implicit loading of IngestionJob.rows (that relationship uses lazy="raise").

create_many — genuinely memory-bounded bulk insert
---------------------------------------------------
Accepts a sequence of RowInsertMapping (a lightweight typed dict alias).
Uses SQLAlchemy Core insert() with bounded batches of dictionaries.

WHY Core INSERT INSTEAD OF ORM add_all():
  ORM add_all() adds every object to the session identity map as pending
  state. For 100,000 rows this means 100,000 Python objects remain in memory
  for the entire unit of work — the "batching" via add_all() slices is purely
  cosmetic if the flush happens once at the end.

  SQLAlchemy Core session.execute(insert(DatasetRow), batch_of_dicts) bypasses
  the identity map entirely. Each batch_of_dicts is sent as a parameterized
  multi-row INSERT statement. After each batch execute() the dicts go out of
  scope (garbage-collected). The session accumulates no ORM-tracked state for
  bulk rows.

WHY RETURN int INSTEAD OF list[DatasetRow]:
  Ingestion workflows do not need 100,000 persisted ORM objects back.
  Returning a full list would require either a round-trip SELECT or retaining
  all objects in memory. Returning the count keeps the interface honest about
  what is actually provided.

BATCH SIZE:
  _INSERT_BATCH_SIZE = 500 rows per Core execute() call.
  Rationale: this is an operational tradeoff, not a driver protocol guarantee.
  Smaller batches bound the size of each parameterized INSERT statement and
  the memory needed to hold one batch of dicts at a time. Larger batches
  reduce round-trips. 500 rows × ~200-byte JSONB payload ≈ 100 KB per batch.
  This is conservative and safe to adjust upward if profiling warrants it.

PRIMARY KEY GENERATION:
  DatasetRow.id is a server-default UUID (gen_random_uuid()). The Core insert
  path does not return IDs unless RETURNING is used. IDs are therefore
  database-generated and are not available after create_many() returns.
  If the caller needs IDs they must query after insertion.

TRANSACTION SEMANTICS:
  All batches execute within the same caller-owned transaction. The repository
  never calls commit(). If a later batch fails with a DB error the caller
  can roll back the entire transaction, including all earlier batches.
  The session is never in autocommit mode.

PAGINATION CONVENTION:
  The project-wide convention (user_repository, ingestion_job_repository,
  dataset_registry_repository) is silent clamping — invalid values are clamped
  to a safe range rather than raising ValueError. This repository follows the
  same convention for consistency:
    offset:  clamped to >= 0
    limit:   clamped to [_MIN_LIMIT, _MAX_LIMIT]
  Callers that pass invalid values receive a valid (possibly empty) result.

BULK DELETE:
  delete_by_ingestion_job() issues a single Core DELETE statement.
  synchronize_session=False is correct because all rows for the given job
  are being removed; no stale per-job ORM objects would be re-used in the
  same unit of work.
"""

from __future__ import annotations

import uuid
from typing import Any, Sequence, cast

from app.models.ingestion import DatasetRow
from sqlalchemy import delete, func, insert, select
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession

# ---------------------------------------------------------------------------
# Internal constants
# ---------------------------------------------------------------------------

_INSERT_BATCH_SIZE: int = 500  # rows per Core execute() call
_DEFAULT_LIMIT: int = 1_000
_MAX_LIMIT: int = 10_000
_MIN_LIMIT: int = 1

# ---------------------------------------------------------------------------
# Typed input for create_many
# ---------------------------------------------------------------------------

# A RowInsertMapping is a plain dict with the required persistence fields.
# It is intentionally lightweight — no ORM overhead, no identity-map tracking.
# Required keys: ingestion_job_id, row_number, values
# Optional keys: (none — all required fields are listed above)
RowInsertMapping = dict[str, Any]


class DatasetRowRepository:
    """Data access layer for DatasetRow entities."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    async def create_many(self, rows: Sequence[RowInsertMapping]) -> int:
        """Bulk-insert dataset rows using bounded Core INSERT batches.

        Parameters
        ----------
        rows:
            A sequence of dicts, each containing:
              ingestion_job_id: UUID
              row_number:       int  (>= 0, unique within the job)
              values:           dict (JSON-compatible key/value pairs)

        Returns
        -------
        int
            The total number of rows inserted.

        Memory behaviour:
            Each batch of _INSERT_BATCH_SIZE dicts is passed to a single
            Core execute(insert(DatasetRow), batch). After execution the
            batch list goes out of scope. No DatasetRow ORM objects are
            created or added to the identity map.

        Transaction behaviour:
            All batches execute within the same caller-owned transaction.
            The repository never calls commit(). If a later batch raises
            a DB error the caller can roll back all earlier batches.

        Primary keys:
            IDs are database-generated (gen_random_uuid()). They are NOT
            returned by this method. Use get_by_row_number() if the caller
            needs a specific row's ID after insertion.
        """
        if not rows:
            return 0

        total = 0
        all_rows = list(rows)

        for batch_start in range(0, len(all_rows), _INSERT_BATCH_SIZE):
            batch = all_rows[batch_start : batch_start + _INSERT_BATCH_SIZE]
            # Core INSERT — no ORM objects created, no identity-map pollution
            await self._session.execute(insert(DatasetRow), batch)
            total += len(batch)

        return total

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    async def get_by_id(self, row_id: uuid.UUID) -> DatasetRow | None:
        """Return a DatasetRow by primary key, or None if not found."""
        result = await self._session.execute(select(DatasetRow).where(DatasetRow.id == row_id))
        return result.scalar_one_or_none()

    async def get_by_row_number(
        self,
        ingestion_job_id: uuid.UUID,
        row_number: int,
    ) -> DatasetRow | None:
        """Return the DatasetRow at a specific row_number within a job, or None."""
        result = await self._session.execute(
            select(DatasetRow).where(
                DatasetRow.ingestion_job_id == ingestion_job_id,
                DatasetRow.row_number == row_number,
            )
        )
        return result.scalar_one_or_none()

    async def list_by_ingestion_job(
        self,
        ingestion_job_id: uuid.UUID,
        *,
        offset: int = 0,
        limit: int = _DEFAULT_LIMIT,
    ) -> list[DatasetRow]:
        """Return a paginated, row_number-ordered slice of rows for a job.

        Ordering is strictly by row_number ASC, reflecting source order.
        Pagination convention: silent clamping (project-wide standard).

        Parameters
        ----------
        offset: clamped to >= 0
        limit:  clamped to [_MIN_LIMIT, _MAX_LIMIT] (max 10,000)
        """
        safe_offset = max(0, offset)
        safe_limit = max(_MIN_LIMIT, min(_MAX_LIMIT, limit))

        result = await self._session.execute(
            select(DatasetRow)
            .where(DatasetRow.ingestion_job_id == ingestion_job_id)
            .order_by(DatasetRow.row_number.asc())
            .offset(safe_offset)
            .limit(safe_limit)
        )
        return list(result.scalars().all())

    async def count_for_job(self, ingestion_job_id: uuid.UUID) -> int:
        """Return the total row count for a job via SELECT COUNT (no objects loaded)."""
        result = await self._session.execute(
            select(func.count())
            .select_from(DatasetRow)
            .where(DatasetRow.ingestion_job_id == ingestion_job_id)
        )
        return result.scalar_one()

    async def exists(
        self,
        ingestion_job_id: uuid.UUID,
        row_number: int,
    ) -> bool:
        """Return True if a row at row_number exists within the job."""
        result = await self._session.execute(
            select(func.count())
            .select_from(DatasetRow)
            .where(
                DatasetRow.ingestion_job_id == ingestion_job_id,
                DatasetRow.row_number == row_number,
            )
        )
        return result.scalar_one() > 0

    # ------------------------------------------------------------------
    # Delete
    # ------------------------------------------------------------------

    async def delete_by_ingestion_job(self, ingestion_job_id: uuid.UUID) -> int:
        """Bulk-delete all rows for a job using a single Core DELETE statement.

        Returns the number of deleted rows. Does NOT load rows first.
        synchronize_session=False is safe here because all rows for this
        specific job are being removed — no stale per-job ORM objects
        would be reused within the same unit of work.
        """
        result = await self._session.execute(
            delete(DatasetRow)
            .where(DatasetRow.ingestion_job_id == ingestion_job_id)
            .execution_options(synchronize_session=False)
        )
        cursor_result = cast(CursorResult[Any], result)
        return int(cursor_result.rowcount or 0)
