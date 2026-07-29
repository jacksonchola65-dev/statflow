from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user, validate_csrf
from app.db.session import get_db
from app.models.user import User
from app.schemas.dashboard import (
    DashboardCreateRequest,
    DashboardListResponse,
    DashboardResponse,
    DashboardUpdateRequest,
)
from app.services.dashboard_service import (
    DashboardNotFoundError,
    DashboardOwnershipError,
    DashboardService,
)

router = APIRouter(prefix="/dashboards", tags=["dashboards"])


@router.get("", response_model=DashboardListResponse)
async def list_dashboards(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> DashboardListResponse:
    svc = DashboardService(db)
    dashboards = await svc.list_dashboards(current_user.id)
    return DashboardListResponse(
        dashboards=[DashboardResponse.model_validate(d) for d in dashboards],
        total=len(dashboards),
    )


@router.get("/{dashboard_id}", response_model=DashboardResponse)
async def get_dashboard(
    dashboard_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> DashboardResponse:
    svc = DashboardService(db)
    try:
        dashboard = await svc.get_dashboard(dashboard_id)
    except DashboardNotFoundError:
        raise HTTPException(status_code=404, detail="Dashboard not found.")

    if dashboard.owner_id != current_user.id:
        raise HTTPException(status_code=403, detail="You do not own this dashboard.")
    return DashboardResponse.model_validate(dashboard)


@router.post("", response_model=DashboardResponse, status_code=status.HTTP_201_CREATED)
async def create_dashboard(
    body: DashboardCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    __: None = Depends(validate_csrf),
) -> DashboardResponse:
    svc = DashboardService(db)
    dashboard = await svc.create_dashboard(
        user_id=current_user.id,
        title=body.title,
        description=body.description,
        cards=[card.model_dump(mode="json") for card in body.cards],
    )
    return DashboardResponse.model_validate(dashboard)


@router.put("/{dashboard_id}", response_model=DashboardResponse)
async def put_dashboard(
    dashboard_id: uuid.UUID,
    body: DashboardUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    __: None = Depends(validate_csrf),
) -> DashboardResponse:
    svc = DashboardService(db)
    try:
        dashboard = await svc.update_dashboard(
            dashboard_id,
            current_user.id,
            title=body.title,
            description=body.description,
            cards=[card.model_dump(mode="json") for card in body.cards]
            if body.cards is not None
            else None,
        )
    except DashboardNotFoundError:
        raise HTTPException(status_code=404, detail="Dashboard not found.")
    except DashboardOwnershipError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    return DashboardResponse.model_validate(dashboard)


@router.patch("/{dashboard_id}", response_model=DashboardResponse)
async def update_dashboard(
    dashboard_id: uuid.UUID,
    body: DashboardUpdateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    __: None = Depends(validate_csrf),
) -> DashboardResponse:
    return await put_dashboard(
        dashboard_id=dashboard_id,
        body=body,
        db=db,
        current_user=current_user,
        __=__,
    )


@router.delete("/{dashboard_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_dashboard(
    dashboard_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
    __: None = Depends(validate_csrf),
) -> None:
    svc = DashboardService(db)
    try:
        await svc.delete_dashboard(dashboard_id, current_user.id)
    except DashboardNotFoundError:
        raise HTTPException(status_code=404, detail="Dashboard not found.")
    except DashboardOwnershipError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
