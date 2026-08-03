from app.models.dataset import Dataset
from app.repositories.dataset_repository import DatasetRepository
from sqlalchemy.ext.asyncio import AsyncSession


class DatasetService:
    def __init__(self, session: AsyncSession) -> None:
        self._repo = DatasetRepository(session)

    async def get_all_datasets(self) -> list[Dataset]:
        """Return all datasets."""
        return await self._repo.get_all_datasets()

    async def get_published_datasets(self) -> list[Dataset]:
        """Return only published datasets."""
        return await self._repo.get_published_datasets()
