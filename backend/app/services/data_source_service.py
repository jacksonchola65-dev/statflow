"""
services/data_source_service.py
================================
Business logic for managing DataSource (publishing organisations).

Transaction ownership: caller (endpoint layer via get_db) commits/rolls back.
The service never calls commit() or rollback().
"""

from __future__ import annotations

import uuid
from typing import Optional

from app.models.data_source import DataSource
from app.repositories.data_source_repository import DataSourceRepository
from sqlalchemy.ext.asyncio import AsyncSession

# ---------------------------------------------------------------------------
# Domain exceptions
# ---------------------------------------------------------------------------


class DataSourceNameConflictError(Exception):
    """Raised when the source name already exists (case-insensitive)."""


class DataSourceNotFoundError(Exception):
    """Raised when no DataSource matches the requested ID."""


class DataSourceHasDatasetsError(Exception):
    """Raised when attempting to delete a DataSource that still owns datasets."""


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class DataSourceService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._repo = DataSourceRepository(session)

    async def list_sources(self, active_only: bool = False) -> list[DataSource]:
        return await self._repo.list_all(active_only=active_only)

    async def get_source(self, source_id: uuid.UUID) -> DataSource:
        src = await self._repo.get_by_id(source_id)
        if src is None:
            raise DataSourceNotFoundError(f"No data source found with id={source_id}.")
        return src

    async def create_source(
        self,
        name: str,
        description: Optional[str] = None,
        organization_type: Optional[str] = None,
        base_url: Optional[str] = None,
        country: Optional[str] = None,
        is_active: bool = True,
    ) -> DataSource:
        if await self._repo.name_exists(name):
            raise DataSourceNameConflictError(f"A data source named '{name}' already exists.")
        return await self._repo.create(
            name=name.strip(),
            description=description,
            organization_type=organization_type,
            base_url=base_url,
            country=country,
            is_active=is_active,
        )

    async def update_source(self, source_id: uuid.UUID, **fields) -> DataSource:
        src = await self._repo.get_by_id(source_id)
        if src is None:
            raise DataSourceNotFoundError(f"No data source found with id={source_id}.")

        new_name = fields.get("name")
        if new_name is not None and await self._repo.name_exists(new_name, exclude_id=source_id):
            raise DataSourceNameConflictError(f"A data source named '{new_name}' already exists.")

        updated = await self._repo.update(source_id, **fields)
        assert updated is not None
        return updated

    async def delete_source(self, source_id: uuid.UUID) -> None:
        src = await self._repo.get_by_id(source_id)
        if src is None:
            raise DataSourceNotFoundError(f"No data source found with id={source_id}.")

        count = await self._repo.count_datasets(source_id)
        if count > 0:
            raise DataSourceHasDatasetsError(
                f"Cannot delete this data source: {count} dataset(s) still reference it."
            )

        deleted = await self._repo.delete(source_id)
        assert deleted
