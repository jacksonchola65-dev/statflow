"""
models/data_source.py
=====================
Two-entity model for the Official Data Integration module.

DataSource
----------
Represents a publishing organisation or data origin (e.g. "Zambia Statistics
Agency", "World Bank"). One DataSource can have many DatasetRegistry records.

DatasetRegistry
---------------
Represents a specific dataset published by a DataSource (e.g. "2022 Census
Population by Province", "Monthly Consumer Price Index"). Contains all
dataset-level metadata plus a foreign key back to its DataSource.

Relationship:  DataSource 1──* DatasetRegistry
"""

from __future__ import annotations

import enum
import uuid
from datetime import date, datetime, timezone
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import Boolean, Date, DateTime, Enum, ForeignKey, String, Text, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.ingestion import IngestionJob


# ---------------------------------------------------------------------------
# Enumerations (dataset-level)
# ---------------------------------------------------------------------------


class SourceType(str, enum.Enum):
    OFFICIAL     = "OFFICIAL"
    ORGANIZATION = "ORGANIZATION"
    INTERNAL     = "INTERNAL"


class FileFormat(str, enum.Enum):
    CSV   = "CSV"
    XLSX  = "XLSX"
    JSON  = "JSON"
    API   = "API"
    OTHER = "OTHER"


class ImportMethod(str, enum.Enum):
    MANUAL    = "MANUAL"
    SCHEDULED = "SCHEDULED"
    API_PULL  = "API_PULL"


class RefreshFrequency(str, enum.Enum):
    DAILY     = "DAILY"
    WEEKLY    = "WEEKLY"
    MONTHLY   = "MONTHLY"
    QUARTERLY = "QUARTERLY"
    ANNUALLY  = "ANNUALLY"
    ADHOC     = "ADHOC"


class VerificationStatus(str, enum.Enum):
    UNVERIFIED = "UNVERIFIED"
    PENDING    = "PENDING"
    VERIFIED   = "VERIFIED"
    REJECTED   = "REJECTED"


# ---------------------------------------------------------------------------
# DataSource — the publishing organisation / data origin
# ---------------------------------------------------------------------------


class DataSource(Base):
    """A publishing organisation or data origin.

    Examples: Zambia Statistics Agency, Bank of Zambia, World Bank.
    """

    __tablename__ = "data_sources"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        unique=True,
        index=True,
    )
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    organization_type: Mapped[Optional[str]] = mapped_column(
        String(100), nullable=True
    )
    base_url: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    country: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=text("true"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Relationship
    datasets: Mapped[List["DatasetRegistry"]] = relationship(
        "DatasetRegistry",
        back_populates="data_source",
        cascade="save-update, merge",   # intentionally NO delete-cascade; use service layer
    )

    def __repr__(self) -> str:
        return f"<DataSource id={self.id} name={self.name!r}>"


# ---------------------------------------------------------------------------
# DatasetRegistry — a specific dataset published by a DataSource
# ---------------------------------------------------------------------------


class DatasetRegistry(Base):
    """A specific dataset published by a DataSource.

    Examples:
    - 2022 Census Population by Province
    - Monthly Consumer Price Index
    - Daily Exchange Rates
    """

    __tablename__ = "dataset_registry"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )

    # Foreign key to publishing organisation
    data_source_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("data_sources.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    # Dataset identification
    dataset_name: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        unique=True,
        index=True,
    )
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Classification
    source_type: Mapped[SourceType] = mapped_column(
        Enum(SourceType, name="source_type_enum", native_enum=True),
        nullable=False,
    )
    category: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    file_format: Mapped[Optional[FileFormat]] = mapped_column(
        Enum(FileFormat, name="file_format_enum", native_enum=True),
        nullable=True,
    )

    # Source location
    source_url: Mapped[Optional[str]] = mapped_column(String(1000), nullable=True)
    publication_date: Mapped[Optional[date]] = mapped_column(Date, nullable=True)

    # Licensing and versioning
    licence: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    version: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    # Import logistics
    import_method: Mapped[Optional[ImportMethod]] = mapped_column(
        Enum(ImportMethod, name="import_method_enum", native_enum=True),
        nullable=True,
    )
    refresh_frequency: Mapped[Optional[RefreshFrequency]] = mapped_column(
        Enum(RefreshFrequency, name="refresh_frequency_enum", native_enum=True),
        nullable=True,
    )
    last_imported_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    # Quality / governance
    verification_status: Mapped[VerificationStatus] = mapped_column(
        Enum(VerificationStatus, name="verification_status_enum", native_enum=True),
        nullable=False,
        default=VerificationStatus.UNVERIFIED,
        server_default=text("'UNVERIFIED'"),
    )

    # Audit timestamps
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Relationship back to publisher
    data_source: Mapped["DataSource"] = relationship(
        "DataSource",
        back_populates="datasets",
    )

    # Relationship to ingestion jobs for this dataset
    # intentionally NO delete-cascade; FK on IngestionJob uses RESTRICT
    ingestion_jobs: Mapped[List["IngestionJob"]] = relationship(
        "IngestionJob",
        back_populates="dataset_registry",
        cascade="save-update, merge",
    )

    def __repr__(self) -> str:
        return (
            f"<DatasetRegistry id={self.id} "
            f"name={self.dataset_name!r} "
            f"source_id={self.data_source_id}>"
        )
