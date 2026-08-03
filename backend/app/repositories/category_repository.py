from app.models.category import Category
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


class CategoryRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_all_categories(self) -> list[Category]:
        """Return all categories ordered alphabetically by name."""
        result = await self._session.execute(select(Category).order_by(Category.name.asc()))
        return list(result.scalars().all())
