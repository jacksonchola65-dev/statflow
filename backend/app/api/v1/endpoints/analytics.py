import logging
import uuid
from asyncio import CancelledError
from typing import Optional

from app.core.dependencies import get_current_user, validate_csrf
from app.db.session import get_db
from app.domain.analytics.contracts import (
    AnalyticsDimensionDescriptor,
    AnalyticsMeasureDescriptor,
    AnalyticsQuery,
    AnalyticsResult,
    DatasetColumnDescriptor,
    DatasetDetails,
    DatasetListResult,
    DatasetPreviewResult,
    DatasetStatistics,
)
from app.domain.analytics.dependencies import (
    get_analytics_service,
    get_dataset_discovery_service,
)
from app.domain.analytics.discovery import DatasetDiscoveryService
from app.domain.analytics.exceptions import (
    AnalyticsQueryError,
    DatasetNotAnalyticsReadyError,
    IncompleteIngestionJobError,
    UnknownIngestionJobError,
)
from app.domain.analytics.service import AnalyticsService
from app.models.user import User
from app.schemas.analytics import IndicatorSummaryResponse
from app.services.analytics_service import AnalyticsService as LegacyAnalyticsService
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.post(
    "/query",
    response_model=AnalyticsResult,
    summary="Execute analytics queries",
    description=(
        "Execute a validated analytics query against a completed ingestion job. "
        "The request body must conform to the AnalyticsQuery contract."
    ),
    responses={
        status.HTTP_400_BAD_REQUEST: {
            "description": "Invalid analytics query or incomplete ingestion job."
        },
        status.HTTP_401_UNAUTHORIZED: {"description": "Authentication required."},
        status.HTTP_404_NOT_FOUND: {"description": "Ingestion job not found."},
        status.HTTP_500_INTERNAL_SERVER_ERROR: {"description": "Unexpected server error."},
    },
)
async def query_analytics(
    query: AnalyticsQuery,
    service: AnalyticsService = Depends(get_analytics_service),
    _: User = Depends(get_current_user),
    __: None = Depends(validate_csrf),
) -> AnalyticsResult:
    try:
        return await service.execute(query)
    except UnknownIngestionJobError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Ingestion job not found.",
        )
    except IncompleteIngestionJobError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Ingestion job is not complete.",
        )
    except AnalyticsQueryError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except CancelledError:
        raise
    except Exception as exc:
        logger.exception(
            "Unexpected analytics query failure",
            extra={
                "ingestion_job_id": str(query.dataset_reference.ingestion_job_id),
                "dimension_count": len(query.dimensions),
                "measure_count": len(query.measures),
                "filter_count": len(query.filters),
                "sort_count": len(query.sorting),
                "limit": query.limit,
                "offset": query.offset,
            },
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred while processing the analytics query.",
        ) from exc


@router.get(
    "/datasets",
    response_model=DatasetListResult,
    summary="List analytics-ready datasets",
    description=(
        "Return a paginated list of analytics-ready datasets. "
        "Only completed ingestion jobs with persisted column metadata are returned."
    ),
    responses={
        status.HTTP_401_UNAUTHORIZED: {"description": "Authentication required."},
        status.HTTP_500_INTERNAL_SERVER_ERROR: {"description": "Unexpected server error."},
    },
)
async def list_analytics_datasets(
    limit: int = Query(
        50,
        ge=1,
        le=100,
        description="Maximum number of datasets to return.",
    ),
    offset: int = Query(
        0,
        ge=0,
        description="Number of datasets to skip.",
    ),
    service: DatasetDiscoveryService = Depends(get_dataset_discovery_service),
    _: User = Depends(get_current_user),
) -> DatasetListResult:
    try:
        return await service.list_datasets(limit=limit, offset=offset)
    except CancelledError:
        raise
    except Exception as exc:
        logger.exception(
            "Unexpected analytics dataset list failure",
            extra={"limit": limit, "offset": offset},
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred while retrieving dataset list.",
        ) from exc


@router.get(
    "/datasets/{ingestion_job_id}",
    response_model=DatasetDetails,
    summary="Retrieve analytics dataset details",
    description=(
        "Return public metadata, schema hints, and discovery metadata for a single "
        "analytics-ready ingestion job."
    ),
    responses={
        status.HTTP_401_UNAUTHORIZED: {"description": "Authentication required."},
        status.HTTP_404_NOT_FOUND: {"description": "Dataset not found."},
        status.HTTP_409_CONFLICT: {"description": "Dataset is not analytics-ready."},
        status.HTTP_500_INTERNAL_SERVER_ERROR: {"description": "Unexpected server error."},
    },
)
async def get_analytics_dataset_details(
    ingestion_job_id: uuid.UUID,
    service: DatasetDiscoveryService = Depends(get_dataset_discovery_service),
    _: User = Depends(get_current_user),
) -> DatasetDetails:
    try:
        return await service.get_dataset_details(ingestion_job_id)
    except UnknownIngestionJobError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Dataset not found.",
        )
    except (IncompleteIngestionJobError, DatasetNotAnalyticsReadyError):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Dataset is not analytics-ready.",
        )
    except CancelledError:
        raise
    except Exception as exc:
        logger.exception(
            "Unexpected analytics dataset details failure",
            extra={"ingestion_job_id": str(ingestion_job_id)},
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred while retrieving dataset details.",
        ) from exc


@router.get(
    "/datasets/{ingestion_job_id}/schema",
    response_model=list[DatasetColumnDescriptor],
    summary="Retrieve dataset schema",
    description=(
        "Return persisted column metadata, data type information, and eligibility "
        "flags for a single analytics-ready dataset."
    ),
    responses={
        status.HTTP_401_UNAUTHORIZED: {"description": "Authentication required."},
        status.HTTP_404_NOT_FOUND: {"description": "Dataset not found."},
        status.HTTP_409_CONFLICT: {"description": "Dataset is not analytics-ready."},
        status.HTTP_500_INTERNAL_SERVER_ERROR: {"description": "Unexpected server error."},
    },
)
async def get_analytics_dataset_schema(
    ingestion_job_id: uuid.UUID,
    service: DatasetDiscoveryService = Depends(get_dataset_discovery_service),
    _: User = Depends(get_current_user),
) -> list[DatasetColumnDescriptor]:
    try:
        return await service.get_schema(ingestion_job_id)
    except UnknownIngestionJobError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Dataset not found.",
        )
    except (IncompleteIngestionJobError, DatasetNotAnalyticsReadyError):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Dataset is not analytics-ready.",
        )
    except CancelledError:
        raise
    except Exception as exc:
        logger.exception(
            "Unexpected analytics dataset schema failure",
            extra={"ingestion_job_id": str(ingestion_job_id)},
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred while retrieving dataset schema.",
        ) from exc


@router.get(
    "/datasets/{ingestion_job_id}/dimensions",
    response_model=list[AnalyticsDimensionDescriptor],
    summary="List available dataset dimensions",
    description=(
        "Return available dimension identifiers and metadata for a single analytics-ready dataset."
    ),
    responses={
        status.HTTP_401_UNAUTHORIZED: {"description": "Authentication required."},
        status.HTTP_404_NOT_FOUND: {"description": "Dataset not found."},
        status.HTTP_409_CONFLICT: {"description": "Dataset is not analytics-ready."},
        status.HTTP_500_INTERNAL_SERVER_ERROR: {"description": "Unexpected server error."},
    },
)
async def get_analytics_dataset_dimensions(
    ingestion_job_id: uuid.UUID,
    service: DatasetDiscoveryService = Depends(get_dataset_discovery_service),
    _: User = Depends(get_current_user),
) -> list[AnalyticsDimensionDescriptor]:
    try:
        return await service.get_dimensions(ingestion_job_id)
    except UnknownIngestionJobError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Dataset not found.",
        )
    except (IncompleteIngestionJobError, DatasetNotAnalyticsReadyError):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Dataset is not analytics-ready.",
        )
    except CancelledError:
        raise
    except Exception as exc:
        logger.exception(
            "Unexpected analytics dataset dimensions failure",
            extra={"ingestion_job_id": str(ingestion_job_id)},
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred while retrieving dataset dimensions.",
        ) from exc


@router.get(
    "/datasets/{ingestion_job_id}/measures",
    response_model=list[AnalyticsMeasureDescriptor],
    summary="List available dataset measures",
    description=(
        "Return available measure identifiers and supported aggregations for a single analytics-ready dataset."
    ),
    responses={
        status.HTTP_401_UNAUTHORIZED: {"description": "Authentication required."},
        status.HTTP_404_NOT_FOUND: {"description": "Dataset not found."},
        status.HTTP_409_CONFLICT: {"description": "Dataset is not analytics-ready."},
        status.HTTP_500_INTERNAL_SERVER_ERROR: {"description": "Unexpected server error."},
    },
)
async def get_analytics_dataset_measures(
    ingestion_job_id: uuid.UUID,
    service: DatasetDiscoveryService = Depends(get_dataset_discovery_service),
    _: User = Depends(get_current_user),
) -> list[AnalyticsMeasureDescriptor]:
    try:
        return await service.get_measures(ingestion_job_id)
    except UnknownIngestionJobError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Dataset not found.",
        )
    except (IncompleteIngestionJobError, DatasetNotAnalyticsReadyError):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Dataset is not analytics-ready.",
        )
    except CancelledError:
        raise
    except Exception as exc:
        logger.exception(
            "Unexpected analytics dataset measures failure",
            extra={"ingestion_job_id": str(ingestion_job_id)},
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred while retrieving dataset measures.",
        ) from exc


@router.get(
    "/datasets/{ingestion_job_id}/preview",
    response_model=DatasetPreviewResult,
    summary="Preview persisted dataset rows",
    description=(
        "Return a safe, bounded preview of persisted rows for a single analytics-ready dataset."
    ),
    responses={
        status.HTTP_401_UNAUTHORIZED: {"description": "Authentication required."},
        status.HTTP_404_NOT_FOUND: {"description": "Dataset not found."},
        status.HTTP_409_CONFLICT: {"description": "Dataset is not analytics-ready."},
        status.HTTP_500_INTERNAL_SERVER_ERROR: {"description": "Unexpected server error."},
    },
)
async def get_analytics_dataset_preview(
    ingestion_job_id: uuid.UUID,
    limit: int = Query(
        10,
        ge=1,
        le=50,
        description="Maximum number of preview rows to return.",
    ),
    service: DatasetDiscoveryService = Depends(get_dataset_discovery_service),
    _: User = Depends(get_current_user),
) -> DatasetPreviewResult:
    try:
        return await service.get_preview(ingestion_job_id, limit=limit)
    except UnknownIngestionJobError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Dataset not found.",
        )
    except (IncompleteIngestionJobError, DatasetNotAnalyticsReadyError):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Dataset is not analytics-ready.",
        )
    except CancelledError:
        raise
    except Exception as exc:
        logger.exception(
            "Unexpected analytics dataset preview failure",
            extra={"ingestion_job_id": str(ingestion_job_id), "limit": limit},
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred while retrieving dataset preview.",
        ) from exc


@router.get(
    "/datasets/{ingestion_job_id}/statistics",
    response_model=DatasetStatistics,
    summary="Retrieve dataset statistics",
    description=("Return affordable persisted statistics for a single analytics-ready dataset."),
    responses={
        status.HTTP_401_UNAUTHORIZED: {"description": "Authentication required."},
        status.HTTP_404_NOT_FOUND: {"description": "Dataset not found."},
        status.HTTP_409_CONFLICT: {"description": "Dataset is not analytics-ready."},
        status.HTTP_500_INTERNAL_SERVER_ERROR: {"description": "Unexpected server error."},
    },
)
async def get_analytics_dataset_statistics(
    ingestion_job_id: uuid.UUID,
    service: DatasetDiscoveryService = Depends(get_dataset_discovery_service),
    _: User = Depends(get_current_user),
) -> DatasetStatistics:
    try:
        return await service.get_statistics(ingestion_job_id)
    except UnknownIngestionJobError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Dataset not found.",
        )
    except (IncompleteIngestionJobError, DatasetNotAnalyticsReadyError):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Dataset is not analytics-ready.",
        )
    except CancelledError:
        raise
    except Exception as exc:
        logger.exception(
            "Unexpected analytics dataset statistics failure",
            extra={"ingestion_job_id": str(ingestion_job_id)},
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred while retrieving dataset statistics.",
        ) from exc


@router.get(
    "/indicator-summary",
    response_model=IndicatorSummaryResponse,
    summary="Province-level indicator summary",
    description=(
        "Returns province-level values for a given indicator and reference year. "
        "Supply dataset_id to target a specific dataset. "
        "Omitting dataset_id will raise HTTP 409 when the same indicator/year "
        "combination exists in more than one dataset."
    ),
)
async def indicator_summary(
    indicator_id: uuid.UUID = Query(..., description="Indicator UUID"),
    reference_year: int = Query(..., ge=1900, le=2100, description="Reference year"),
    dataset_id: Optional[uuid.UUID] = Query(
        default=None, description="Optional dataset UUID to resolve ambiguity"
    ),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
) -> IndicatorSummaryResponse:
    service = LegacyAnalyticsService(db)
    return await service.get_indicator_summary(
        indicator_id=indicator_id,
        reference_year=reference_year,
        dataset_id=dataset_id,
    )
