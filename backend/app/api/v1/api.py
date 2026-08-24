from app.api.v1.endpoints import (
    analytics,
    auth,
    categories,
    dashboards,
    data_points,
    data_sources,
    dataset_registry,
    datasets,
    decisions,
    districts,
    health,
    imports,
    indicators,
    ingestions,
    provinces,
    users,
)
from fastapi import APIRouter

api_router = APIRouter()

api_router.include_router(health.router)
api_router.include_router(auth.router)
api_router.include_router(provinces.router)
api_router.include_router(districts.router)
api_router.include_router(categories.router)
api_router.include_router(indicators.router)
api_router.include_router(datasets.router)
api_router.include_router(data_points.router)
api_router.include_router(analytics.router)
api_router.include_router(imports.router)
api_router.include_router(ingestions.router)
api_router.include_router(users.router)
api_router.include_router(data_sources.router)
api_router.include_router(dataset_registry.router)
api_router.include_router(dashboards.router)
api_router.include_router(decisions.router)
