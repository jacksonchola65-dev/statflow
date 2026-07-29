import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.district import District
from app.repositories.district_repository import DistrictRepository


class DistrictService:
    def __init__(self, session: AsyncSession) -> None:
        self._repo = DistrictRepository(session)

    async def get_all_districts(self) -> list[District]:
        """Return all districts ordered by name."""
        return await self._repo.get_all_districts()

    async def get_districts_by_province(
        self, province_id: uuid.UUID
    ) -> list[District]:
        """Return districts for a given province, ordered by name."""
        return await self._repo.get_districts_by_province(province_id)
