"""
endpoints/data_sources.py
==========================
CRUD for DataSource (publishing organisations).

Routes:
  GET    /data-sources            — list
  GET    /data-sources/{id}       — get single
  POST   /data-sources            — create (DATA_MANAGER or ADMIN + CSRF)
  PATCH  /data-sources/{id}       — update (DATA_MANAGER or ADMIN + CSRF)
  DELETE /data-sources/{id}       — delete (ADMIN + CSRF; 409 if datasets exist)
"""

from __future__ import annotations

import uuid

from app.core.dependencies import (
    get_current_user,
    require_admin,
    require_data_manager_or_admin,
    validate_csrf,
)
from app.db.session import get_db
from app.models.user import User
from app.schemas.data_source import (
    DataSourceCreateRequest,
    DataSourceListResponse,
    DataSourceResponse,
    DataSourceUpdateRequest,
)
from app.services.data_source_service import (
    DataSourceHasDatasetsError,
    DataSourceNameConflictError,
    DataSourceNotFoundError,
    DataSourceService,
)
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/data-sources", tags=["data-sources"])


@router.get("", response_model=DataSourceListResponse)
async def list_data_sources(
    active_only: bool = Query(default=False),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
) -> DataSourceListResponse:
    svc = DataSourceService(db)
    sources = await svc.list_sources(active_only=active_only)
    return DataSourceListResponse(
        sources=[DataSourceResponse.model_validate(s) for s in sources],
        total=len(sources),
    )


@router.get("/{source_id}", response_model=DataSourceResponse)
async def get_data_source(
    source_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
) -> DataSourceResponse:
    svc = DataSourceService(db)
    try:
        src = await svc.get_source(source_id)
    except DataSourceNotFoundError:
        raise HTTPException(status_code=404, detail="Data source not found.")
    return DataSourceResponse.model_validate(src)


@router.post("", response_model=DataSourceResponse, status_code=status.HTTP_201_CREATED)
async def create_data_source(
    body: DataSourceCreateRequest,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_data_manager_or_admin),
    __: None = Depends(validate_csrf),
) -> DataSourceResponse:
    svc = DataSourceService(db)
    try:
        src = await svc.create_source(
            name=body.name,
            description=body.description,
            organization_type=body.organization_type,
            base_url=body.base_url,
            country=body.country,
            is_active=body.is_active,
        )
    except DataSourceNameConflictError:
        raise HTTPException(status_code=409, detail="A data source with that name already exists.")
    return DataSourceResponse.model_validate(src)


@router.patch("/{source_id}", response_model=DataSourceResponse)
async def update_data_source(
    source_id: uuid.UUID,
    body: DataSourceUpdateRequest,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_data_manager_or_admin),
    __: None = Depends(validate_csrf),
) -> DataSourceResponse:
    svc = DataSourceService(db)
    fields = body.model_dump(exclude_unset=True)
    try:
        src = await svc.update_source(source_id, **fields)
    except DataSourceNotFoundError:
        raise HTTPException(status_code=404, detail="Data source not found.")
    except DataSourceNameConflictError:
        raise HTTPException(status_code=409, detail="A data source with that name already exists.")
    return DataSourceResponse.model_validate(src)


@router.delete("/{source_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_data_source(
    source_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_admin),
    __: None = Depends(validate_csrf),
) -> None:
    svc = DataSourceService(db)
    try:
        await svc.delete_source(source_id)
    except DataSourceNotFoundError:
        raise HTTPException(status_code=404, detail="Data source not found.")
    except DataSourceHasDatasetsError:
        raise HTTPException(
            status_code=409, detail="This data source is still in use and cannot be deleted."
        )
