from app.core.dependencies import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.province import ProvinceResponse
from app.services.province_service import ProvinceService
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter()


@router.get(
    "/provinces",
    response_model=list[ProvinceResponse],
    summary="List all provinces",
    description=(
        "Returns all provinces in Zambia ordered alphabetically by name. "
        "Each province includes its unique identifier, code, and name."
    ),
    tags=["provinces"],
)
async def list_provinces(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
) -> list[ProvinceResponse]:
    service = ProvinceService(db)
    return await service.get_all_provinces()
