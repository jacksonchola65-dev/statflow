import uuid

from pydantic import BaseModel


class DistrictResponse(BaseModel):
    id: uuid.UUID
    province_id: uuid.UUID
    code: str
    name: str

    model_config = {"from_attributes": True}
