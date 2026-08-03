import uuid
from typing import Optional

from app.models.data_point import DataPoint
from sqlalchemy import asc, select
from sqlalchemy.ext.asyncio import AsyncSession


class DataPointRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_data_points(
        self,
        dataset_id: Optional[uuid.UUID] = None,
        indicator_id: Optional[uuid.UUID] = None,
        province_id: Optional[uuid.UUID] = None,
        district_id: Optional[uuid.UUID] = None,
        reference_year: Optional[int] = None,
    ) -> list[DataPoint]:
        """
        Return data points matching all supplied filters.
        Filters are optional and combinable.
        Results are ordered by reference_year ASC, then created_at ASC.
        """
        stmt = select(DataPoint)

        if dataset_id is not None:
            stmt = stmt.where(DataPoint.dataset_id == dataset_id)
        if indicator_id is not None:
            stmt = stmt.where(DataPoint.indicator_id == indicator_id)
        if province_id is not None:
            stmt = stmt.where(DataPoint.province_id == province_id)
        if district_id is not None:
            stmt = stmt.where(DataPoint.district_id == district_id)
        if reference_year is not None:
            stmt = stmt.where(DataPoint.reference_year == reference_year)

        stmt = stmt.order_by(
            asc(DataPoint.reference_year),
            asc(DataPoint.created_at),
        )

        result = await self._session.execute(stmt)
        return list(result.scalars().all())
