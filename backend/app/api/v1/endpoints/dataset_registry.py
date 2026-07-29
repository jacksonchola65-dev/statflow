"""
endpoints/dataset_registry.py
==============================
CRUD for DatasetRegistry (individual datasets).

Routes:
  GET    /dataset-registry            — list (with optional filters)
  GET    /dataset-registry/{id}       — get single
  POST   /dataset-registry            — create (DATA_MANAGER or ADMIN + CSRF)
  PATCH  /dataset-registry/{id}       — update (DATA_MANAGER or ADMIN + CSRF)
  DELETE /dataset-registry/{id}       — delete (DATA_MANAGER or ADMIN + CSRF)
"""

from __future__ import annotations

import uuid
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import (
    get_current_user,
    require_data_manager_or_admin,
    validate_csrf,
)
from app.db.session import get_db
from app.models.data_source import SourceType, VerificationStatus
from app.models.user import User
from app.schemas.data_source import (
    DatasetRegistryCreateRequest,
    DatasetRegistryListResponse,
    DatasetRegistryResponse,
    DatasetRegistryUpdateRequest,
)
from app.services.dataset_registry_service import (
    DatasetNameConflictError,
    DatasetNotFoundError,
    DataSourceNotFoundForDatasetError,
    DatasetRegistryService,
)

router = APIRouter(prefix="/dataset-registry", tags=["dataset-registry"])


@router.get("", response_model=DatasetRegistryListResponse)
async def list_datasets(
    data_source_id: Optional[uuid.UUID] = Query(default=None),
    source_type: Optional[SourceType] = Query(default=None),
    verification_status: Optional[VerificationStatus] = Query(default=None),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
) -> DatasetRegistryListResponse:
    svc = DatasetRegistryService(db)
    entries = await svc.list_datasets(
        data_source_id=data_source_id,
        source_type=source_type,
        verification_status=verification_status,
    )
    return DatasetRegistryListResponse(
        datasets=[DatasetRegistryResponse.model_validate(e) for e in entries],
        total=len(entries),
    )


@router.get("/{entry_id}", response_model=DatasetRegistryResponse)
async def get_dataset(
    entry_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
) -> DatasetRegistryResponse:
    svc = DatasetRegistryService(db)
    try:
        entry = await svc.get_dataset(entry_id)
    except DatasetNotFoundError:
        raise HTTPException(status_code=404, detail="Dataset not found.")
    return DatasetRegistryResponse.model_validate(entry)


@router.post(
    "", response_model=DatasetRegistryResponse, status_code=status.HTTP_201_CREATED
)
async def create_dataset(
    body: DatasetRegistryCreateRequest,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_data_manager_or_admin),
    __: None = Depends(validate_csrf),
) -> DatasetRegistryResponse:
    svc = DatasetRegistryService(db)
    try:
        entry = await svc.create_dataset(
            data_source_id=body.data_source_id,
            dataset_name=body.dataset_name,
            source_type=body.source_type,
            description=body.description,
            category=body.category,
            file_format=body.file_format,
            source_url=body.source_url,
            publication_date=body.publication_date,
            licence=body.licence,
            version=body.version,
            import_method=body.import_method,
            refresh_frequency=body.refresh_frequency,
            last_imported_at=body.last_imported_at,
            verification_status=body.verification_status,
        )
    except DataSourceNotFoundForDatasetError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except DatasetNameConflictError as e:
        raise HTTPException(status_code=409, detail=str(e))
    return DatasetRegistryResponse.model_validate(entry)


@router.patch("/{entry_id}", response_model=DatasetRegistryResponse)
async def update_dataset(
    entry_id: uuid.UUID,
    body: DatasetRegistryUpdateRequest,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_data_manager_or_admin),
    __: None = Depends(validate_csrf),
) -> DatasetRegistryResponse:
    svc = DatasetRegistryService(db)
    fields = body.model_dump(exclude_unset=True)
    try:
        entry = await svc.update_dataset(entry_id, **fields)
    except DatasetNotFoundError:
        raise HTTPException(status_code=404, detail="Dataset not found.")
    except DataSourceNotFoundForDatasetError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except DatasetNameConflictError as e:
        raise HTTPException(status_code=409, detail=str(e))
    return DatasetRegistryResponse.model_validate(entry)


@router.delete("/{entry_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_dataset(
    entry_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_data_manager_or_admin),
    __: None = Depends(validate_csrf),
) -> None:
    svc = DatasetRegistryService(db)
    try:
        await svc.delete_dataset(entry_id)
    except DatasetNotFoundError:
        raise HTTPException(status_code=404, detail="Dataset not found.")
