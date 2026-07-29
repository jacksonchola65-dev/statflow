import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.data_point import DataPointResponse
from app.services.data_point_service import DataPointService

router = APIRouter()


@router.get(
    "/data-points",
    response_model=list[DataPointResponse],
    summary="List data points",
    description=(
        "Returns data points ordered by reference_year ascending, then created_at ascending. "
        "All query parameters are optional and combinable. "
        "Supplying both province_id and district_id is not allowed and returns HTTP 422."
    ),
    tags=["data-points"],
)
async def list_data_points(
    dataset_id: Optional[uuid.UUID] = Query(default=None),
    indicator_id: Optional[uuid.UUID] = Query(default=None),
    province_id: Optional[uuid.UUID] = Query(default=None),
    district_id: Optional[uuid.UUID] = Query(default=None),
    reference_year: Optional[int] = Query(default=None, ge=1900, le=2100),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
) -> list[DataPointResponse]:
    if province_id is not None and district_id is not None:
        raise HTTPException(
            status_code=422,
            detail=(
                "province_id and district_id cannot both be supplied. "
                "A data point belongs to exactly one geographic level."
            ),
        )

    service = DataPointService(db)
    return await service.get_data_points(
        dataset_id=dataset_id,
        indicator_id=indicator_id,
        province_id=province_id,
        district_id=district_id,
        reference_year=reference_year,
    )
