import uuid

from app.models.district import District
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


class DistrictRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_all_districts(self) -> list[District]:
        """Return all districts ordered alphabetically by name."""
        result = await self._session.execute(select(District).order_by(District.name.asc()))
        return list(result.scalars().all())

    async def get_districts_by_province(self, province_id: uuid.UUID) -> list[District]:
        """Return districts for a specific province, ordered alphabetically by name."""
        result = await self._session.execute(
            select(District)
            .where(District.province_id == province_id)
            .order_by(District.name.asc())
        )
        return list(result.scalars().all())
