"""
schemas/ingestion.py
====================
Pydantic v2 response schemas for ingestion inspection and results.

These schemas expose persisted ingestion data:
- IngestionJobSummaryResponse: metadata of a completed ingestion run
- DatasetColumnResponse: column metadata inferred during inspection
- DatasetRowResponse: persisted data rows
- DatasetInspectionResponse: composite job + columns + rows + pagination
- IngestionResultResponse: result of IngestionPersistenceService

All schemas use from_attributes=True for ORM model loading.
UUID, datetime, and enums are preserved in their types.
Decimal strings are preserved as strings (not converted to float).
Row values (JSONB) are preserved exactly as stored.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from app.models.data_source import FileFormat
from app.models.ingestion import InferredColumnType, IngestionStatus
from pydantic import BaseModel, ConfigDict, Field

# ---------------------------------------------------------------------------
# Pagination
# ---------------------------------------------------------------------------


class PaginationResponse(BaseModel):
    """Standard pagination metadata."""

    page: int = Field(ge=1, description="Current page number (1-indexed)")
    page_size: int = Field(ge=1, le=10_000, description="Number of items per page")
    total_items: int = Field(ge=0, description="Total number of items")
    total_pages: int = Field(ge=0, description="Total number of pages")
    has_next: bool = Field(description="Whether a next page exists")
    has_previous: bool = Field(description="Whether a previous page exists")


# ---------------------------------------------------------------------------
# IngestionJobSummaryResponse
# ---------------------------------------------------------------------------


class IngestionJobSummaryResponse(BaseModel):
    """Metadata of a completed ingestion job."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    dataset_registry_id: uuid.UUID
    status: IngestionStatus
    original_filename: str
    file_format: Optional[FileFormat]
    row_count: Optional[int]
    column_count: Optional[int]
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    failed_at: Optional[datetime]
    error_message: Optional[str]
    created_by_user_id: Optional[uuid.UUID]
    created_at: datetime
    updated_at: datetime


# ---------------------------------------------------------------------------
# DatasetColumnResponse
# ---------------------------------------------------------------------------


class DatasetColumnResponse(BaseModel):
    """Column-level metadata inferred during file inspection."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    ingestion_job_id: uuid.UUID
    ordinal_position: int
    original_name: str
    normalized_name: str
    inferred_type: InferredColumnType
    nullable: bool
    missing_count: int
    unique_count: int
    sample_values: Optional[list]
    created_at: datetime


# ---------------------------------------------------------------------------
# DatasetRowResponse
# ---------------------------------------------------------------------------


class DatasetRowResponse(BaseModel):
    """A single data row persisted after inspection."""

    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    ingestion_job_id: uuid.UUID
    row_number: int
    values: dict
    created_at: datetime


# ---------------------------------------------------------------------------
# DatasetInspectionResponse
# ---------------------------------------------------------------------------


class DatasetInspectionResponse(BaseModel):
    """Complete inspection results: job metadata + columns + rows + pagination."""

    job: IngestionJobSummaryResponse
    columns: list[DatasetColumnResponse]
    rows: list[DatasetRowResponse]
    pagination: PaginationResponse


# ---------------------------------------------------------------------------
# IngestionResultResponse
# ---------------------------------------------------------------------------


class IngestionResultResponse(BaseModel):
    """Result of persisting an ingestion profile via IngestionPersistenceService."""

    ingestion_job_id: uuid.UUID
    columns_inserted: int
    rows_inserted: int
    final_status: IngestionStatus
