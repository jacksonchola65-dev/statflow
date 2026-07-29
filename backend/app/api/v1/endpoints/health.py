from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter()


class HealthResponse(BaseModel):
    status: str
    service: str


@router.get(
    "/health",
    response_model=HealthResponse,
    summary="Health check",
    description="Returns the current health status of the API.",
    tags=["health"],
)
async def health_check() -> HealthResponse:
    return HealthResponse(status="healthy", service="statflow-api")
