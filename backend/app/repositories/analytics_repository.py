import uuid
from dataclasses import dataclass
from decimal import Decimal
from typing import Optional

from app.models.data_point import DataPoint
from app.models.province import Province
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


@dataclass
class ProvinceRow:
    province_id: uuid.UUID
    province_code: str
    province_name: str
    value: Decimal
    dataset_id: uuid.UUID


class AnalyticsRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_province_indicator_rows(
        self,
        indicator_id: uuid.UUID,
        reference_year: int,
        dataset_id: Optional[uuid.UUID] = None,
    ) -> list[ProvinceRow]:
        """
        Join data_points with provinces.

        Filters:
        - province-level rows only (province_id IS NOT NULL AND district_id IS NULL)
        - indicator_id and reference_year always applied
        - dataset_id applied when supplied

        Results ordered alphabetically by province name.
        """
        stmt = (
            select(
                DataPoint.dataset_id,
                DataPoint.value,
                Province.id.label("province_id"),
                Province.code.label("province_code"),
                Province.name.label("province_name"),
            )
            .join(Province, DataPoint.province_id == Province.id)
            .where(
                DataPoint.indicator_id == indicator_id,
                DataPoint.reference_year == reference_year,
                DataPoint.province_id.isnot(None),
                DataPoint.district_id.is_(None),
            )
            .order_by(Province.name.asc())
        )

        if dataset_id is not None:
            stmt = stmt.where(DataPoint.dataset_id == dataset_id)

        result = await self._session.execute(stmt)
        rows = result.all()

        return [
            ProvinceRow(
                province_id=row.province_id,
                province_code=row.province_code,
                province_name=row.province_name,
                value=Decimal(str(row.value)),
                dataset_id=row.dataset_id,
            )
            for row in rows
        ]
