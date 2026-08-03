from app.core.dependencies import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.dataset import DatasetResponse
from app.services.dataset_service import DatasetService
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter()


@router.get(
    "/datasets",
    response_model=list[DatasetResponse],
    summary="List datasets",
    description=(
        "Returns datasets ordered by reference year descending (null years last), "
        "then name alphabetically. "
        "Set `published_only=true` to return only published datasets."
    ),
    tags=["datasets"],
)
async def list_datasets(
    published_only: bool = Query(
        default=False,
        description="When true, return only published datasets.",
    ),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
) -> list[DatasetResponse]:
    service = DatasetService(db)
    if published_only:
        return await service.get_published_datasets()
    return await service.get_all_datasets()
