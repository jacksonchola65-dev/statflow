import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.indicator import Indicator
from app.repositories.indicator_repository import IndicatorRepository


class IndicatorService:
    def __init__(self, session: AsyncSession) -> None:
        self._repo = IndicatorRepository(session)

    async def get_all_indicators(self) -> list[Indicator]:
        """Return all indicators ordered by name."""
        return await self._repo.get_all_indicators()

    async def get_indicators_by_category(
        self, category_id: uuid.UUID
    ) -> list[Indicator]:
        """Return indicators for a given category, ordered by name."""
        return await self._repo.get_indicators_by_category(category_id)
