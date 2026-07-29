import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class DatasetResponse(BaseModel):
    id: uuid.UUID
    name: str
    description: Optional[str] = None
    source_name: Optional[str] = None
    source_url: Optional[str] = None
    reference_year: Optional[int] = None
    is_published: bool
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}
