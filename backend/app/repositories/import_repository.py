"""
import_repository.py
====================
Database access layer for the CSV import pipeline.

Design constraints
------------------
- Follows the existing StatFlow repository pattern:
    class FooRepository:
        def __init__(self, session: AsyncSession) -> None: ...
- Methods NEVER call session.commit() or session.rollback().
  The caller (ImportService.confirm) owns the transaction boundary via
  ``async with session.begin()``.
- session.flush() IS used inside create_dataset_if_absent to force the
  server-side id generation before the caller needs the new Dataset.id.
- No business logic — only data access.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import TYPE_CHECKING

from sqlalchemy import func, select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.data_point import DataPoint
from app.models.dataset import Dataset
from app.models.indicator import Indicator
from app.models.province import Province

if TYPE_CHECKING:
    from app.utils.csv_parser import ParsedRow


# ---------------------------------------------------------------------------
# Value objects
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DatasetResolution:
    """
    Returned by ImportRepository.create_dataset_if_absent().

    dataset : the Dataset record (existing or newly created and flushed)
    created : True if a new Dataset row was inserted; False if an existing
              record was found and returned unchanged.
    """

    dataset: Dataset
    created: bool


# ---------------------------------------------------------------------------
# Value object for a conflicting natural key
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ConflictKey:
    """
    Identifies a DataPoint whose natural key already exists in the database.

    dataset_id, indicator_id, province_id, and reference_year together form
    the province-level unique index:
        uix_data_points_province_level

    dataset_name is the human-readable name from the CSV row, included so
    the preview response can identify which dataset each conflict belongs to
    without requiring a second database lookup.
    """

    dataset_id: uuid.UUID
    indicator_id: uuid.UUID
    province_id: uuid.UUID
    reference_year: int
    dataset_name: str = ""   # populated by the service at preview time


# ---------------------------------------------------------------------------
# Repository
# ---------------------------------------------------------------------------


class ImportRepository:
    """Data access layer used exclusively by ImportService."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ------------------------------------------------------------------
    # Lookup loaders — used by ImportService.preview()
    # ------------------------------------------------------------------

    async def load_province_map(self) -> dict[str, uuid.UUID]:
        """
        Return {province.code.upper(): province.id} for all provinces.

        The parser compares province codes case-insensitively, so upper-casing
        here is the single source of truth.
        """
        result = await self._session.execute(
            select(Province.code, Province.id)
        )
        return {row.code.upper(): row.id for row in result.all()}

    async def load_indicator_map(self) -> dict[str, uuid.UUID]:
        """
        Return {indicator.code.upper(): indicator.id} for all indicators.
        """
        result = await self._session.execute(
            select(Indicator.code, Indicator.id)
        )
        return {row.code.upper(): row.id for row in result.all()}

    async def load_dataset_names(self) -> set[str]:
        """
        Return the set of existing Dataset.name values (original casing).

        The parser uses this set to decide whether source_name is required
        (required only when the dataset_name is new, i.e. not in this set).
        The parser handles case-insensitive comparison itself.
        """
        result = await self._session.execute(select(Dataset.name))
        return {row.name for row in result.all()}

    # ------------------------------------------------------------------
    # Dataset resolution — used by ImportService.confirm()
    # ------------------------------------------------------------------

    async def find_dataset_by_name(self, name: str) -> Dataset | None:
        """
        Look up an existing Dataset by name, case-insensitively.

        Uses PostgreSQL's ``lower()`` function so that 'Survey2023' and
        'SURVEY2023' resolve to the same record.  The canonical (existing)
        record is returned unchanged; its stored name is not modified.

        Returns None if no Dataset matches.
        """
        result = await self._session.execute(
            select(Dataset).where(
                func.lower(func.trim(Dataset.name)) == name.strip().lower()
            )
        )
        return result.scalar_one_or_none()

    async def create_dataset_if_absent(
        self,
        dataset_name: str,
        source_name: str | None,
        source_url: str | None,
    ) -> DatasetResolution:
        """
        Return a DatasetResolution for the given dataset_name.

        - If a Dataset already exists whose name matches case-insensitively
          (after trimming), return DatasetResolution(dataset=existing, created=False).
          The existing record is never modified.
        - If no match is found, create a new Dataset, flush it (so the
          server-generated id is available), and return
          DatasetResolution(dataset=new, created=True).

        This method never calls session.commit() or session.rollback().
        The caller owns the transaction via ``async with session.begin()``.
        """
        existing = await self.find_dataset_by_name(dataset_name)
        if existing is not None:
            return DatasetResolution(dataset=existing, created=False)

        new_dataset = Dataset(
            name=dataset_name.strip(),
            source_name=source_name,
            source_url=source_url,
        )
        self._session.add(new_dataset)
        await self._session.flush()  # populates new_dataset.id
        return DatasetResolution(dataset=new_dataset, created=True)

    # ------------------------------------------------------------------
    # Conflict detection — used by ImportService.preview()
    # ------------------------------------------------------------------

    async def check_conflicts(
        self,
        dataset_id: uuid.UUID,
        rows: list["ParsedRow"],
    ) -> list[ConflictKey]:
        """
        Return a list of ConflictKey for every row whose province-level
        natural key already exists in data_points for the given dataset.

        Natural key (province-level):
            (dataset_id, indicator_id, province_id, reference_year)

        The query uses a single batch IN check against the database partial
        unique index to avoid N+1 queries.

        Only province-level rows are checked here (district_id IS NULL).
        This is consistent with the CSV import scope (province-level only).

        An empty list means no conflicts.
        """
        if not rows:
            return []

        # Build the set of (indicator_id, province_id, reference_year) tuples
        # to check against the given dataset_id.
        tuples_to_check = [
            (row.indicator_id, row.province_id, row.reference_year)
            for row in rows
        ]

        stmt = (
            select(
                DataPoint.indicator_id,
                DataPoint.province_id,
                DataPoint.reference_year,
            )
            .where(
                DataPoint.dataset_id == dataset_id,
                DataPoint.province_id.isnot(None),
                DataPoint.district_id.is_(None),
                tuple_(
                    DataPoint.indicator_id,
                    DataPoint.province_id,
                    DataPoint.reference_year,
                ).in_(tuples_to_check),
            )
        )

        result = await self._session.execute(stmt)
        return [
            ConflictKey(
                dataset_id=dataset_id,
                indicator_id=row.indicator_id,
                province_id=row.province_id,
                reference_year=row.reference_year,
            )
            for row in result.all()
        ]

    # ------------------------------------------------------------------
    # Bulk insert — used by ImportService.confirm()
    # ------------------------------------------------------------------

    async def bulk_insert_data_points(
        self,
        dataset_id: uuid.UUID,
        rows: list["ParsedRow"],
    ) -> int:
        """
        Insert all validated rows as province-level DataPoint records.

        Uses session.add_all() + session.flush() inside the caller's
        transaction.  Does NOT commit.  The caller (ImportService.confirm)
        owns the ``async with session.begin()`` context.

        Each DataPoint has:
            dataset_id    = dataset_id (caller-supplied)
            indicator_id  = row.indicator_id
            province_id   = row.province_id
            district_id   = None  (province-level only for CSV imports)
            value         = row.value
            reference_year = row.reference_year

        Returns the count of inserted rows.
        """
        if not rows:
            return 0

        data_points = [
            DataPoint(
                dataset_id=dataset_id,
                indicator_id=row.indicator_id,
                province_id=row.province_id,
                district_id=None,
                value=row.value,
                reference_year=row.reference_year,
            )
            for row in rows
        ]

        self._session.add_all(data_points)
        await self._session.flush()  # validates constraints; does NOT commit
        return len(data_points)
