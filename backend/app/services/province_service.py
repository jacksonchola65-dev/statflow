from sqlalchemy.ext.asyncio import AsyncSession

from app.models.province import Province
from app.repositories.province_repository import ProvinceRepository


class ProvinceService:
    def __init__(self, session: AsyncSession) -> None:
        self._repo = ProvinceRepository(session)

    async def get_all_provinces(self) -> list[Province]:
        """Return all provinces ordered by name."""
        return await self._repo.get_all_provinces()
