from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.dashboard import Dashboard


class DashboardRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_for_user(self, user_id: uuid.UUID) -> list[Dashboard]:
        result = await self._session.execute(
            select(Dashboard)
            .options(selectinload(Dashboard.cards))
            .options(selectinload(Dashboard.owner))
            .where(Dashboard.owner_id == user_id)
            .order_by(Dashboard.updated_at.desc(), Dashboard.id.asc())
        )
        return list(result.scalars().all())

    async def get_by_id(self, dashboard_id: uuid.UUID) -> Dashboard | None:
        result = await self._session.execute(
            select(Dashboard)
            .options(selectinload(Dashboard.cards))
            .options(selectinload(Dashboard.owner))
            .where(Dashboard.id == dashboard_id)
        )
        return result.scalar_one_or_none()

    async def create(self, **kwargs) -> Dashboard:
        dashboard = Dashboard(**kwargs)
        self._session.add(dashboard)
        await self._session.flush()
        await self._session.refresh(dashboard)
        return dashboard

    async def update(self, dashboard_id: uuid.UUID, **fields) -> Dashboard | None:
        dashboard = await self.get_by_id(dashboard_id)
        if dashboard is None:
            return None
        for key, value in fields.items():
            setattr(dashboard, key, value)
        return dashboard

    async def delete(self, dashboard_id: uuid.UUID) -> bool:
        dashboard = await self.get_by_id(dashboard_id)
        if dashboard is None:
            return False
        await self._session.delete(dashboard)
        return True
