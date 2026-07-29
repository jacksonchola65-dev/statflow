import uuid
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.district import DistrictResponse
from app.services.district_service import DistrictService

router = APIRouter()


@router.get(
    "/districts",
    response_model=list[DistrictResponse],
    summary="List districts",
    description=(
        "Returns districts ordered alphabetically by name. "
        "Optionally filter by province using the `province_id` query parameter."
    ),
    tags=["districts"],
)
async def list_districts(
    province_id: Optional[uuid.UUID] = Query(
        default=None,
        description="Filter districts by province UUID.",
    ),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
) -> list[DistrictResponse]:
    service = DistrictService(db)
    if province_id is not None:
        return await service.get_districts_by_province(province_id)
    return await service.get_all_districts()
