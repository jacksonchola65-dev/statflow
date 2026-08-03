"""
repositories/dataset_registry_repository.py
============================================
Data access layer for DatasetRegistry (individual datasets).

Follows the StatFlow repository pattern:
- No commit() or rollback().
- flush() used after add() to populate generated UUIDs.
- No business logic or HTTP exceptions.
"""

from __future__ import annotations

import uuid
from typing import Optional

from app.models.data_source import DatasetRegistry, SourceType, VerificationStatus
from sqlalchemy import asc, func, select
from sqlalchemy.ext.asyncio import AsyncSession


class DatasetRegistryRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    async def get_by_id(self, entry_id: uuid.UUID) -> Optional[DatasetRegistry]:
        result = await self._session.execute(
            select(DatasetRegistry).where(DatasetRegistry.id == entry_id)
        )
        return result.scalar_one_or_none()

    async def list_all(
        self,
        data_source_id: Optional[uuid.UUID] = None,
        source_type: Optional[SourceType] = None,
        verification_status: Optional[VerificationStatus] = None,
    ) -> list[DatasetRegistry]:
        stmt = select(DatasetRegistry)
        if data_source_id is not None:
            stmt = stmt.where(DatasetRegistry.data_source_id == data_source_id)
        if source_type is not None:
            stmt = stmt.where(DatasetRegistry.source_type == source_type)
        if verification_status is not None:
            stmt = stmt.where(DatasetRegistry.verification_status == verification_status)
        stmt = stmt.order_by(asc(DatasetRegistry.dataset_name))
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def name_exists(self, dataset_name: str, exclude_id: Optional[uuid.UUID] = None) -> bool:
        stmt = (
            select(func.count())
            .select_from(DatasetRegistry)
            .where(
                func.lower(func.trim(DatasetRegistry.dataset_name)) == dataset_name.strip().lower()
            )
        )
        if exclude_id is not None:
            stmt = stmt.where(DatasetRegistry.id != exclude_id)
        result = await self._session.execute(stmt)
        return result.scalar_one() > 0

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    async def create(self, **kwargs) -> DatasetRegistry:
        entry = DatasetRegistry(**kwargs)
        self._session.add(entry)
        await self._session.flush()
        return entry

    async def update(self, entry_id: uuid.UUID, **fields) -> Optional[DatasetRegistry]:
        entry = await self.get_by_id(entry_id)
        if entry is None:
            return None
        for key, value in fields.items():
            setattr(entry, key, value)
        return entry

    async def delete(self, entry_id: uuid.UUID) -> bool:
        entry = await self.get_by_id(entry_id)
        if entry is None:
            return False
        await self._session.delete(entry)
        return True
