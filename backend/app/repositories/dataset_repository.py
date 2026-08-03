from app.models.dataset import Dataset
from sqlalchemy import asc, desc, nulls_last, select
from sqlalchemy.ext.asyncio import AsyncSession


def _order_clause():
    """
    Ordering rule:
      1. reference_year DESC, NULLs last
      2. name ASC
    """
    return (
        nulls_last(desc(Dataset.reference_year)),
        asc(Dataset.name),
    )


class DatasetRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_all_datasets(self) -> list[Dataset]:
        """Return all datasets ordered by year desc (nulls last), then name asc."""
        result = await self._session.execute(select(Dataset).order_by(*_order_clause()))
        return list(result.scalars().all())

    async def get_published_datasets(self) -> list[Dataset]:
        """Return only published datasets, same ordering."""
        result = await self._session.execute(
            select(Dataset).where(Dataset.is_published.is_(True)).order_by(*_order_clause())
        )
        return list(result.scalars().all())
