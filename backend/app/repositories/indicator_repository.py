import uuid

from app.models.indicator import Indicator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


class IndicatorRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_all_indicators(self) -> list[Indicator]:
        """Return all indicators ordered alphabetically by name."""
        result = await self._session.execute(select(Indicator).order_by(Indicator.name.asc()))
        return list(result.scalars().all())

    async def get_indicators_by_category(self, category_id: uuid.UUID) -> list[Indicator]:
        """Return indicators for a specific category, ordered alphabetically by name."""
        result = await self._session.execute(
            select(Indicator)
            .where(Indicator.category_id == category_id)
            .order_by(Indicator.name.asc())
        )
        return list(result.scalars().all())
