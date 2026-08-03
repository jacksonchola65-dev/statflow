from __future__ import annotations

from app.core.dependencies import get_db
from app.domain.analytics.discovery import (
    DatasetDiscoveryRepository,
    DatasetDiscoveryService,
)
from app.domain.analytics.planner import AnalyticsQueryPlanner
from app.domain.analytics.repository import AnalyticsRepository
from app.domain.analytics.service import AnalyticsService
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession


def get_analytics_query_planner(db: AsyncSession = Depends(get_db)) -> AnalyticsQueryPlanner:
    return AnalyticsQueryPlanner(db)


def get_analytics_repository(db: AsyncSession = Depends(get_db)) -> AnalyticsRepository:
    return AnalyticsRepository(db)


def get_analytics_service(
    planner: AnalyticsQueryPlanner = Depends(get_analytics_query_planner),
    repository: AnalyticsRepository = Depends(get_analytics_repository),
) -> AnalyticsService:
    return AnalyticsService(planner, repository)


def get_analytics_discovery_repository(
    db: AsyncSession = Depends(get_db),
) -> DatasetDiscoveryRepository:
    return DatasetDiscoveryRepository(db)


def get_dataset_discovery_service(
    repository: DatasetDiscoveryRepository = Depends(get_analytics_discovery_repository),
) -> DatasetDiscoveryService:
    return DatasetDiscoveryService(repository)
