import uuid
from datetime import datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel


class DataPointResponse(BaseModel):
    id: uuid.UUID
    dataset_id: uuid.UUID
    indicator_id: uuid.UUID
    province_id: Optional[uuid.UUID] = None
    district_id: Optional[uuid.UUID] = None
    value: Decimal
    reference_year: int
    created_at: datetime

    model_config = {"from_attributes": True}
