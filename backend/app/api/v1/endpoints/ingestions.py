from __future__ import annotations

import uuid

from app.core.dependencies import require_data_manager_or_admin
from app.db.session import get_db
from app.models.user import User
from app.schemas.ingestion import DatasetInspectionResponse
from app.services.ingestion_inspection_service import (
    IngestionInspectionService,
    IngestionJobNotFoundError,
    InvalidInspectionPaginationError,
)
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/ingestions", tags=["ingestions"])


@router.get(
    "/{ingestion_job_id}",
    response_model=DatasetInspectionResponse,
    status_code=200,
    summary="Retrieve persisted dataset inspection results",
    description=(
        "Return paginated persisted inspection results for a completed ingestion "
        "job. Requires an authenticated data manager or admin user."
    ),
)
async def get_ingestion_inspection(
    ingestion_job_id: uuid.UUID,
    page: int = Query(
        1,
        ge=1,
        description="1-indexed page number for row pagination.",
    ),
    page_size: int = Query(
        50,
        ge=1,
        le=10000,
        description="Number of rows to return in the response.",
    ),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_data_manager_or_admin),
) -> DatasetInspectionResponse:
    try:
        service = IngestionInspectionService(db)
        return await service.get_inspection(
            ingestion_job_id=ingestion_job_id,
            page=page,
            page_size=page_size,
        )
    except IngestionJobNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Inspection record not found.",
        )
    except InvalidInspectionPaginationError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invalid inspection pagination parameters.",
        )
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unexpected inspection error.",
        )
