import logging

from app.core.metrics import READINESS
from app.db.session import get_engine
from fastapi import APIRouter, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from sqlalchemy import text

# Compatibility alias for tests that monkeypatch "app.api.v1.endpoints.health.engine".
engine = None


def get_health_engine():
    global engine
    if engine is None:
        engine = get_engine()
    elif hasattr(engine, "sync_engine") and engine is not get_engine():
        engine = get_engine()
    return engine


logger = logging.getLogger(__name__)

router = APIRouter()


class HealthResponse(BaseModel):
    status: str
    service: str


class ReadinessResponse(BaseModel):
    status: str
    service: str
    database: str


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Health check",
    description="Returns the current health status of the API.",
    tags=["health"],
)
async def health_check() -> HealthResponse:
    return HealthResponse(status="healthy", service="statflow-api")


@router.get(
    "/ready",
    response_model=ReadinessResponse,
    summary="Readiness check",
    description="Checks whether the API can reach its PostgreSQL database.",
    tags=["health"],
)
async def readiness_check() -> JSONResponse:
    try:
        async with get_health_engine().connect() as conn:
            await conn.execute(text("SELECT 1"))
    except Exception:
        READINESS.set(0)
        logger.exception("Database readiness probe failed")
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={
                "status": "not_ready",
                "service": "statflow-api",
                "database": "unavailable",
            },
        )

    READINESS.set(1)
    return JSONResponse(
        status_code=status.HTTP_200_OK,
        content={
            "status": "ready",
            "service": "statflow-api",
            "database": "ready",
        },
    )
