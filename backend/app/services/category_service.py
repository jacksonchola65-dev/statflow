from app.models.category import Category
from app.repositories.category_repository import CategoryRepository
from sqlalchemy.ext.asyncio import AsyncSession


class CategoryService:
    def __init__(self, session: AsyncSession) -> None:
        self._repo = CategoryRepository(session)

    async def get_all_categories(self) -> list[Category]:
        """Return all categories ordered by name."""
        return await self._repo.get_all_categories()
