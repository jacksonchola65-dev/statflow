"""
schemas/data_source.py
======================
Pydantic v2 schemas for DataSource (publisher) and DatasetRegistry (dataset).
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Optional

from app.models.data_source import (
    FileFormat,
    ImportMethod,
    RefreshFrequency,
    SourceType,
    VerificationStatus,
)
from pydantic import BaseModel, ConfigDict, Field

# ---------------------------------------------------------------------------
# DataSource schemas
# ---------------------------------------------------------------------------


class DataSourceCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: Optional[str] = None
    organization_type: Optional[str] = Field(default=None, max_length=100)
    base_url: Optional[str] = Field(default=None, max_length=1000)
    country: Optional[str] = Field(default=None, max_length=100)
    is_active: bool = True


class DataSourceUpdateRequest(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    description: Optional[str] = None
    organization_type: Optional[str] = Field(default=None, max_length=100)
    base_url: Optional[str] = Field(default=None, max_length=1000)
    country: Optional[str] = Field(default=None, max_length=100)
    is_active: Optional[bool] = None


class DataSourceResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    description: Optional[str]
    organization_type: Optional[str]
    base_url: Optional[str]
    country: Optional[str]
    is_active: bool
    created_at: datetime
    updated_at: datetime


class DataSourceListResponse(BaseModel):
    sources: list[DataSourceResponse]
    total: int


# ---------------------------------------------------------------------------
# DatasetRegistry schemas
# ---------------------------------------------------------------------------


class DatasetRegistryCreateRequest(BaseModel):
    data_source_id: uuid.UUID
    dataset_name: str = Field(min_length=1, max_length=255)
    source_type: SourceType
    description: Optional[str] = None
    category: Optional[str] = Field(default=None, max_length=100)
    file_format: Optional[FileFormat] = None
    source_url: Optional[str] = Field(default=None, max_length=1000)
    publication_date: Optional[date] = None
    licence: Optional[str] = Field(default=None, max_length=200)
    version: Optional[str] = Field(default=None, max_length=100)
    import_method: Optional[ImportMethod] = None
    refresh_frequency: Optional[RefreshFrequency] = None
    last_imported_at: Optional[datetime] = None
    verification_status: VerificationStatus = VerificationStatus.UNVERIFIED


class DatasetRegistryUpdateRequest(BaseModel):
    data_source_id: Optional[uuid.UUID] = None
    dataset_name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    source_type: Optional[SourceType] = None
    description: Optional[str] = None
    category: Optional[str] = Field(default=None, max_length=100)
    file_format: Optional[FileFormat] = None
    source_url: Optional[str] = Field(default=None, max_length=1000)
    publication_date: Optional[date] = None
    licence: Optional[str] = Field(default=None, max_length=200)
    version: Optional[str] = Field(default=None, max_length=100)
    import_method: Optional[ImportMethod] = None
    refresh_frequency: Optional[RefreshFrequency] = None
    last_imported_at: Optional[datetime] = None
    verification_status: Optional[VerificationStatus] = None


class DatasetRegistryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    data_source_id: uuid.UUID
    dataset_name: str
    source_type: SourceType
    description: Optional[str]
    category: Optional[str]
    file_format: Optional[FileFormat]
    source_url: Optional[str]
    publication_date: Optional[date]
    licence: Optional[str]
    version: Optional[str]
    import_method: Optional[ImportMethod]
    refresh_frequency: Optional[RefreshFrequency]
    last_imported_at: Optional[datetime]
    verification_status: VerificationStatus
    created_at: datetime
    updated_at: datetime


class DatasetRegistryListResponse(BaseModel):
    datasets: list[DatasetRegistryResponse]
    total: int
