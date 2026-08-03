from app.models.province import Province
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


class ProvinceRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_all_provinces(self) -> list[Province]:
        """Return all provinces ordered alphabetically by name."""
        result = await self._session.execute(select(Province).order_by(Province.name.asc()))
        return list(result.scalars().all())
