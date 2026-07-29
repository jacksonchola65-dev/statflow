import uuid
from typing import Optional

from pydantic import BaseModel


class IndicatorResponse(BaseModel):
    id: uuid.UUID
    category_id: uuid.UUID
    code: str
    name: str
    description: Optional[str] = None
    unit: Optional[str] = None
    source_name: Optional[str] = None

    model_config = {"from_attributes": True}
