from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user
from app.db.session import get_db
from app.models.user import User
from app.schemas.category import CategoryResponse
from app.services.category_service import CategoryService

router = APIRouter()


@router.get(
    "/categories",
    response_model=list[CategoryResponse],
    summary="List all categories",
    description=(
        "Returns all indicator categories ordered alphabetically by name. "
        "Each category includes its unique identifier, code, name, and optional description."
    ),
    tags=["categories"],
)
async def list_categories(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
) -> list[CategoryResponse]:
    service = CategoryService(db)
    return await service.get_all_categories()
