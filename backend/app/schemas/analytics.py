import uuid
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel


class ProvinceIndicatorResult(BaseModel):
    province_id: uuid.UUID
    province_code: str
    province_name: str
    value: Decimal

    model_config = {"from_attributes": True}


class IndicatorSummaryResponse(BaseModel):
    indicator_id: uuid.UUID
    dataset_id: Optional[uuid.UUID]
    reference_year: int
    unit: Optional[str]
    results: list[ProvinceIndicatorResult]
