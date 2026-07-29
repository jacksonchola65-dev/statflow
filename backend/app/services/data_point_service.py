import uuid
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.data_point import DataPoint
from app.repositories.data_point_repository import DataPointRepository


class DataPointService:
    def __init__(self, session: AsyncSession) -> None:
        self._repo = DataPointRepository(session)

    async def get_data_points(
        self,
        dataset_id: Optional[uuid.UUID] = None,
        indicator_id: Optional[uuid.UUID] = None,
        province_id: Optional[uuid.UUID] = None,
        district_id: Optional[uuid.UUID] = None,
        reference_year: Optional[int] = None,
    ) -> list[DataPoint]:
        """Return data points matching all supplied filters."""
        return await self._repo.get_data_points(
            dataset_id=dataset_id,
            indicator_id=indicator_id,
            province_id=province_id,
            district_id=district_id,
            reference_year=reference_year,
        )
