"""
models/ingestion.py
===================
IngestionJob and DatasetColumn models for the ingestion pipeline.

IngestionJob  — tracks a single file-inspection run against a DatasetRegistry entry.
DatasetColumn — stores column metadata inferred during inspection.

Relationships:
  DatasetRegistry 1──* IngestionJob 1──* DatasetColumn
  ON DELETE RESTRICT for DatasetRegistry → IngestionJob  (NOT NULL FK; every job must belong to a registry)
  ON DELETE CASCADE  for IngestionJob    → DatasetColumn
  ON DELETE SET NULL for User            → IngestionJob   (preserve history if user hard-deleted)

FileFormat note:
  The reused FileFormat enum (CSV, XLSX, JSON, API, OTHER) is defined on DatasetRegistry.
  The ingestion service explicitly restricts uploads to CSV and XLSX only.
  The additional values (JSON, API, OTHER) are retained because DatasetRegistry depends on them.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Enum,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.models.data_source import FileFormat  # reuse existing enum

if TYPE_CHECKING:
    from app.models.data_source import DatasetRegistry
    from app.models.user import User


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------


class IngestionStatus(str, enum.Enum):
    PENDING    = "PENDING"
    PROCESSING = "PROCESSING"
    COMPLETED  = "COMPLETED"
    FAILED     = "FAILED"


class InferredColumnType(str, enum.Enum):
    INTEGER  = "INTEGER"
    DECIMAL  = "DECIMAL"
    BOOLEAN  = "BOOLEAN"
    DATE     = "DATE"
    DATETIME = "DATETIME"
    TEXT     = "TEXT"


# ---------------------------------------------------------------------------
# IngestionJob
# ---------------------------------------------------------------------------


class IngestionJob(Base):
    """Tracks a single file-inspection run for a registered dataset."""

    __tablename__ = "ingestion_jobs"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )

    # FK → dataset_registry; NOT NULL — every job must belong to an existing registry entry.
    # RESTRICT prevents deletion of a registry row that has associated jobs.
    # Source provenance is mandatory: the inspect endpoint requires dataset_registry_id.
    dataset_registry_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("dataset_registry.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    status: Mapped[IngestionStatus] = mapped_column(
        Enum(IngestionStatus, name="ingestion_status_enum", native_enum=True),
        nullable=False,
        default=IngestionStatus.PENDING,
        server_default=text("'PENDING'"),
    )

    original_filename: Mapped[str] = mapped_column(String(500), nullable=False)
    stored_filename: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    # Reuse the canonical FileFormat enum from data_source.py
    file_format: Mapped[Optional[FileFormat]] = mapped_column(
        Enum(FileFormat, name="file_format_enum", native_enum=True),
        nullable=True,
    )

    file_size_bytes: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    row_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    column_count: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    started_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    failed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # FK → users; nullable so ingestion history survives soft-deleted or hard-deleted users
    # SET NULL: if a user record is ever hard-deleted, preserve the job row
    created_by_user_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
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

    __table_args__ = (
        CheckConstraint(
            "file_size_bytes >= 0",
            name="ck_ingestion_jobs_file_size_bytes_non_negative",
        ),
        CheckConstraint(
            "row_count >= 0",
            name="ck_ingestion_jobs_row_count_non_negative",
        ),
        CheckConstraint(
            "column_count >= 0",
            name="ck_ingestion_jobs_column_count_non_negative",
        ),
        Index("ix_ingestion_jobs_status", "status"),
        Index("ix_ingestion_jobs_created_at", "created_at"),
    )

    # Relationship — cascade deletes columns when job is deleted
    columns: Mapped[List["DatasetColumn"]] = relationship(
        "DatasetColumn",
        back_populates="ingestion_job",
        cascade="all, delete-orphan",
    )

    # Relationship — cascade deletes stored rows when job is deleted.
    # lazy="raise" prevents accidental implicit loading of up to 100,000 rows.
    # Rows must be retrieved via explicit paginated SELECT queries.
    # passive_deletes=True tells SQLAlchemy to rely on the database's
    # ON DELETE CASCADE rather than loading every row before deletion.
    rows: Mapped[List["DatasetRow"]] = relationship(
        "DatasetRow",
        back_populates="ingestion_job",
        cascade="all, delete-orphan",
        passive_deletes=True,
        lazy="raise",
    )

    # Relationship back to DatasetRegistry (required — every job belongs to a registry entry)
    dataset_registry: Mapped["DatasetRegistry"] = relationship(
        "DatasetRegistry",
        back_populates="ingestion_jobs",
    )

    # Relationship back to creating User (many-to-one; no collection on User)
    created_by: Mapped[Optional["User"]] = relationship(
        "User",
        foreign_keys=[created_by_user_id],
        lazy="select",
    )

    def __repr__(self) -> str:
        return (
            f"<IngestionJob id={self.id} "
            f"status={self.status} "
            f"file={self.original_filename!r}>"
        )


# ---------------------------------------------------------------------------
# DatasetColumn
# ---------------------------------------------------------------------------


class DatasetColumn(Base):
    """Column-level metadata inferred during a file inspection."""

    __tablename__ = "dataset_columns"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )

    # FK → ingestion_jobs; CASCADE deletion
    ingestion_job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("ingestion_jobs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Zero-based position of this column in the original source file.
    # Position 0 is the leftmost column. The service layer is responsible for
    # assigning contiguous zero-based positions; the repository does not enforce
    # contiguity — that is business validation, not data-access validation.
    ordinal_position: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    original_name: Mapped[str] = mapped_column(String(500), nullable=False)
    normalized_name: Mapped[str] = mapped_column(String(500), nullable=False)

    inferred_type: Mapped[InferredColumnType] = mapped_column(
        Enum(InferredColumnType, name="inferred_column_type_enum", native_enum=True),
        nullable=False,
        default=InferredColumnType.TEXT,
        server_default=text("'TEXT'"),
    )

    nullable: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=text("false"),
    )
    missing_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    unique_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )

    # Up to 5 safe sample values, stored as a JSON array of strings
    sample_values: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )

    __table_args__ = (
        CheckConstraint(
            "length(original_name) > 0",
            name="ck_dataset_columns_original_name_not_empty",
        ),
        CheckConstraint(
            "length(normalized_name) > 0",
            name="ck_dataset_columns_normalized_name_not_empty",
        ),
        CheckConstraint(
            "missing_count >= 0",
            name="ck_dataset_columns_missing_count_non_negative",
        ),
        CheckConstraint(
            "unique_count >= 0",
            name="ck_dataset_columns_unique_count_non_negative",
        ),
        CheckConstraint(
            "ordinal_position >= 0",
            name="ck_dataset_columns_ordinal_position_non_negative",
        ),
        UniqueConstraint(
            "ingestion_job_id",
            "normalized_name",
            name="uq_dataset_columns_job_normalized_name",
        ),
        UniqueConstraint(
            "ingestion_job_id",
            "ordinal_position",
            name="uq_dataset_columns_job_ordinal_position",
        ),
    )

    # Relationship back to job
    ingestion_job: Mapped["IngestionJob"] = relationship(
        "IngestionJob",
        back_populates="columns",
    )

    def __repr__(self) -> str:
        return (
            f"<DatasetColumn id={self.id} "
            f"name={self.normalized_name!r} "
            f"type={self.inferred_type}>"
        )


# ---------------------------------------------------------------------------
# DatasetRow
# ---------------------------------------------------------------------------


class DatasetRow(Base):
    """A single data row persisted after an ingestion job is approved.

    Row values are stored as a PostgreSQL JSONB object whose keys are the
    normalized column names produced during inspection, and whose values are
    JSON-compatible scalars (null, bool, int, float, string).

    Indexing strategy:
    - The composite index (ingestion_job_id, row_number) supports both
      "give me all rows for this job" and "give me row N for this job" queries.
    - An index on ingestion_job_id alone is redundant because the composite
      index covers it; therefore only the composite index is defined.

    Relationship loading:
    - The IngestionJob.rows relationship uses lazy="select" to prevent
      accidental loading of up to 100,000 rows. Callers must use explicit
      paginated SELECT queries when reading rows at scale.
    """

    __tablename__ = "dataset_rows"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )

    # FK → ingestion_jobs; CASCADE deletion — rows belong to a job
    ingestion_job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("ingestion_jobs.id", ondelete="CASCADE"),
        nullable=False,
    )

    # Zero-based row number matching the position in the original source file
    # (0 = first data row after the header).
    row_number: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    # JSONB object: {"<normalized_column_name>": <JSON-compatible value>}
    # Must be a JSON object (not an array or scalar).
    # The CHECK constraint enforces object type at the DB level using
    # the jsonb_typeof() function available in PostgreSQL >= 9.4.
    values: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )

    __table_args__ = (
        CheckConstraint(
            "row_number >= 0",
            name="ck_dataset_rows_row_number_non_negative",
        ),
        CheckConstraint(
            "jsonb_typeof(values) = 'object'",
            name="ck_dataset_rows_values_is_object",
        ),
        UniqueConstraint(
            "ingestion_job_id",
            "row_number",
            name="uq_dataset_rows_job_row_number",
        ),
        # No separate index on (ingestion_job_id, row_number) is needed here.
        # PostgreSQL automatically creates a B-tree index backing the unique
        # constraint above, which supports:
        #   - Left-prefix filtering: WHERE ingestion_job_id = ?
        #   - Ordered lookups:       WHERE ingestion_job_id = ? ORDER BY row_number
        # A duplicate explicit index would increase write overhead with no benefit.
    )

    # Relationship back to job
    ingestion_job: Mapped["IngestionJob"] = relationship(
        "IngestionJob",
        back_populates="rows",
    )

    def __repr__(self) -> str:
        return (
            f"<DatasetRow job={self.ingestion_job_id} "
            f"row={self.row_number}>"
        )
