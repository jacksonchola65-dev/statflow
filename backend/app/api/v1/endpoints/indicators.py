import uuid
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.indicator import IndicatorResponse
from app.services.indicator_service import IndicatorService

router = APIRouter()


@router.get(
    "/indicators",
    response_model=list[IndicatorResponse],
    summary="List indicators",
    description=(
        "Returns indicators ordered alphabetically by name. "
        "Optionally filter by category using the `category_id` query parameter."
    ),
    tags=["indicators"],
)
async def list_indicators(
    category_id: Optional[uuid.UUID] = Query(
        default=None,
        description="Filter indicators by category UUID.",
    ),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
) -> list[IndicatorResponse]:
    service = IndicatorService(db)
    if category_id is not None:
        return await service.get_indicators_by_category(category_id)
    return await service.get_all_indicators()
