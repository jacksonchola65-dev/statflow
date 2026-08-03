"""
services/dataset_registry_service.py
======================================
Business logic for managing DatasetRegistry (individual datasets).

Transaction ownership: caller (endpoint layer via get_db) commits/rolls back.
The service never calls commit() or rollback().
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Optional

from app.models.data_source import (
    DatasetRegistry,
    FileFormat,
    ImportMethod,
    RefreshFrequency,
    SourceType,
    VerificationStatus,
)
from app.repositories.data_source_repository import DataSourceRepository
from app.repositories.dataset_registry_repository import DatasetRegistryRepository
from sqlalchemy.ext.asyncio import AsyncSession

# ---------------------------------------------------------------------------
# Domain exceptions
# ---------------------------------------------------------------------------


class DatasetNameConflictError(Exception):
    """Raised when dataset_name already exists (case-insensitive)."""


class DatasetNotFoundError(Exception):
    """Raised when no DatasetRegistry entry matches the requested ID."""


class DataSourceNotFoundForDatasetError(Exception):
    """Raised when the referenced data_source_id does not exist."""


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class DatasetRegistryService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._repo = DatasetRegistryRepository(session)
        self._src_repo = DataSourceRepository(session)

    async def list_datasets(
        self,
        data_source_id: Optional[uuid.UUID] = None,
        source_type: Optional[SourceType] = None,
        verification_status: Optional[VerificationStatus] = None,
    ) -> list[DatasetRegistry]:
        return await self._repo.list_all(
            data_source_id=data_source_id,
            source_type=source_type,
            verification_status=verification_status,
        )

    async def get_dataset(self, entry_id: uuid.UUID) -> DatasetRegistry:
        entry = await self._repo.get_by_id(entry_id)
        if entry is None:
            raise DatasetNotFoundError(f"No dataset found with id={entry_id}.")
        return entry

    async def create_dataset(
        self,
        data_source_id: uuid.UUID,
        dataset_name: str,
        source_type: SourceType,
        description: Optional[str] = None,
        category: Optional[str] = None,
        file_format: Optional[FileFormat] = None,
        source_url: Optional[str] = None,
        publication_date: Optional[date] = None,
        licence: Optional[str] = None,
        version: Optional[str] = None,
        import_method: Optional[ImportMethod] = None,
        refresh_frequency: Optional[RefreshFrequency] = None,
        last_imported_at: Optional[datetime] = None,
        verification_status: VerificationStatus = VerificationStatus.UNVERIFIED,
    ) -> DatasetRegistry:
        # Validate data_source_id exists
        src = await self._src_repo.get_by_id(data_source_id)
        if src is None:
            raise DataSourceNotFoundForDatasetError(
                f"No data source found with id={data_source_id}."
            )

        # Validate unique dataset_name
        if await self._repo.name_exists(dataset_name):
            raise DatasetNameConflictError(f"A dataset named '{dataset_name}' already exists.")

        return await self._repo.create(
            data_source_id=data_source_id,
            dataset_name=dataset_name.strip(),
            source_type=source_type,
            description=description,
            category=category,
            file_format=file_format,
            source_url=source_url,
            publication_date=publication_date,
            licence=licence,
            version=version,
            import_method=import_method,
            refresh_frequency=refresh_frequency,
            last_imported_at=last_imported_at,
            verification_status=verification_status,
        )

    async def update_dataset(self, entry_id: uuid.UUID, **fields) -> DatasetRegistry:
        entry = await self._repo.get_by_id(entry_id)
        if entry is None:
            raise DatasetNotFoundError(f"No dataset found with id={entry_id}.")

        # Validate new data_source_id if being changed
        new_src_id = fields.get("data_source_id")
        if new_src_id is not None:
            src = await self._src_repo.get_by_id(new_src_id)
            if src is None:
                raise DataSourceNotFoundForDatasetError(
                    f"No data source found with id={new_src_id}."
                )

        # Validate unique dataset_name if being changed
        new_name = fields.get("dataset_name")
        if new_name is not None and await self._repo.name_exists(new_name, exclude_id=entry_id):
            raise DatasetNameConflictError(f"A dataset named '{new_name}' already exists.")

        updated = await self._repo.update(entry_id, **fields)
        assert updated is not None
        return updated

    async def delete_dataset(self, entry_id: uuid.UUID) -> None:
        deleted = await self._repo.delete(entry_id)
        if not deleted:
            raise DatasetNotFoundError(f"No dataset found with id={entry_id}.")
