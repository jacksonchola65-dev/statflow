"""
repositories/data_source_repository.py
=======================================
Data access layer for DataSource (publishing organisations).

Follows the StatFlow repository pattern:
- No commit() or rollback() — caller owns the transaction.
- flush() used after add() to populate generated UUIDs.
- No business logic or HTTP exceptions.
"""

from __future__ import annotations

import uuid
from typing import Optional

from sqlalchemy import asc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.data_source import DataSource


class DataSourceRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ------------------------------------------------------------------
    # Read
    # ------------------------------------------------------------------

    async def get_by_id(self, source_id: uuid.UUID) -> Optional[DataSource]:
        result = await self._session.execute(
            select(DataSource).where(DataSource.id == source_id)
        )
        return result.scalar_one_or_none()

    async def get_by_name(self, name: str) -> Optional[DataSource]:
        result = await self._session.execute(
            select(DataSource).where(
                func.lower(func.trim(DataSource.name)) == name.strip().lower()
            )
        )
        return result.scalar_one_or_none()

    async def list_all(self, active_only: bool = False) -> list[DataSource]:
        stmt = select(DataSource)
        if active_only:
            stmt = stmt.where(DataSource.is_active.is_(True))
        stmt = stmt.order_by(asc(DataSource.name))
        result = await self._session.execute(stmt)
        return list(result.scalars().all())

    async def name_exists(
        self, name: str, exclude_id: Optional[uuid.UUID] = None
    ) -> bool:
        stmt = select(func.count()).select_from(DataSource).where(
            func.lower(func.trim(DataSource.name)) == name.strip().lower()
        )
        if exclude_id is not None:
            stmt = stmt.where(DataSource.id != exclude_id)
        result = await self._session.execute(stmt)
        return result.scalar_one() > 0

    async def count_datasets(self, source_id: uuid.UUID) -> int:
        """Count how many DatasetRegistry rows point to this DataSource."""
        from app.models.data_source import DatasetRegistry
        result = await self._session.execute(
            select(func.count()).select_from(DatasetRegistry).where(
                DatasetRegistry.data_source_id == source_id
            )
        )
        return result.scalar_one()

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    async def create(self, **kwargs) -> DataSource:
        source = DataSource(**kwargs)
        self._session.add(source)
        await self._session.flush()
        return source

    async def update(
        self, source_id: uuid.UUID, **fields
    ) -> Optional[DataSource]:
        source = await self.get_by_id(source_id)
        if source is None:
            return None
        for key, value in fields.items():
            setattr(source, key, value)
        return source

    async def delete(self, source_id: uuid.UUID) -> bool:
        source = await self.get_by_id(source_id)
        if source is None:
            return False
        await self._session.delete(source)
        return True
