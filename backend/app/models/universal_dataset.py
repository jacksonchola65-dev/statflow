from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Optional

from app.db.base import Base
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

if TYPE_CHECKING:
    from app.models.user import User


class UniversalDataset(Base):
    __tablename__ = "universal_datasets"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    owner_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False, index=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    source_filename: Mapped[str] = mapped_column(String(500), nullable=False)
    status: Mapped[str] = mapped_column(
        String(50), nullable=False, default="draft", server_default=text("'draft'")
    )
    current_version_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("universal_dataset_versions.id", ondelete="SET NULL"),
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

    owner: Mapped["User"] = relationship(
        "User", foreign_keys=[owner_id], back_populates="universal_datasets"
    )
    versions: Mapped[list["UniversalDatasetVersion"]] = relationship(
        "UniversalDatasetVersion",
        back_populates="dataset",
        cascade="all, delete-orphan",
        passive_deletes=True,
        lazy="select",
        foreign_keys="[UniversalDatasetVersion.dataset_id]",
    )
    current_version: Mapped[Optional["UniversalDatasetVersion"]] = relationship(
        "UniversalDatasetVersion",
        foreign_keys=[current_version_id],
        primaryjoin="UniversalDataset.current_version_id == UniversalDatasetVersion.id",
        post_update=True,
        uselist=False,
    )

    def __repr__(self) -> str:
        return f"<Dataset id={self.id} name={self.name!r}>"


class UniversalDatasetVersion(Base):
    __tablename__ = "universal_dataset_versions"

    __table_args__ = (
        UniqueConstraint(
            "dataset_id", "version_number", name="uq_universal_dataset_versions_dataset_version"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    dataset_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("universal_datasets.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    version_number: Mapped[int] = mapped_column(Integer, nullable=False)
    row_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    column_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0, server_default=text("0")
    )
    schema_json: Mapped[dict] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    source_type: Mapped[str] = mapped_column(
        String(50), nullable=False, default="csv", server_default=text("'csv'")
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )

    dataset: Mapped["UniversalDataset"] = relationship(
        "UniversalDataset",
        back_populates="versions",
        foreign_keys=[dataset_id],
        primaryjoin="UniversalDatasetVersion.dataset_id == UniversalDataset.id",
    )
    columns: Mapped[list["UniversalDatasetColumn"]] = relationship(
        "UniversalDatasetColumn",
        back_populates="dataset_version",
        cascade="all, delete-orphan",
        passive_deletes=True,
        lazy="select",
    )
    rows: Mapped[list["UniversalDatasetRow"]] = relationship(
        "UniversalDatasetRow",
        back_populates="dataset_version",
        cascade="all, delete-orphan",
        passive_deletes=True,
        lazy="select",
    )

    def __repr__(self) -> str:
        return f"<DatasetVersion id={self.id} version={self.version_number}>"


class UniversalDatasetColumn(Base):
    __tablename__ = "universal_dataset_columns"

    __table_args__ = (
        UniqueConstraint(
            "dataset_version_id", "name", name="uq_universal_dataset_columns_version_name"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    dataset_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("universal_dataset_versions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    original_name: Mapped[str] = mapped_column(String(500), nullable=False)
    inferred_type: Mapped[str] = mapped_column(String(50), nullable=False)
    semantic_type: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    ordinal_position: Mapped[int] = mapped_column(Integer, nullable=False)
    nullable: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    metadata_json: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    dataset_version: Mapped["UniversalDatasetVersion"] = relationship(
        "UniversalDatasetVersion", back_populates="columns"
    )

    def __repr__(self) -> str:
        return f"<DatasetColumn id={self.id} name={self.name!r}>"


class UniversalDatasetRow(Base):
    __tablename__ = "universal_dataset_rows"

    __table_args__ = (
        CheckConstraint("row_number > 0", name="ck_universal_dataset_rows_row_number_positive"),
        UniqueConstraint(
            "dataset_version_id", "row_number", name="uq_universal_dataset_rows_version_row_number"
        ),
        Index(
            "ix_universal_dataset_rows_dataset_version_id_row_number",
            "dataset_version_id",
            "row_number",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    dataset_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("universal_dataset_versions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    row_number: Mapped[int] = mapped_column(Integer, nullable=False)
    data_json: Mapped[dict] = mapped_column(JSONB, nullable=False)
    row_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )

    dataset_version: Mapped["UniversalDatasetVersion"] = relationship(
        "UniversalDatasetVersion",
        back_populates="rows",
    )

    def __init__(
        self,
        *,
        dataset_version_id: uuid.UUID,
        row_number: int,
        data_json: dict,
        row_hash: Optional[str] = None,
    ) -> None:
        self.dataset_version_id = dataset_version_id
        self.row_number = row_number
        self.data_json = data_json
        self.row_hash = row_hash or self._build_row_hash(data_json)

    @staticmethod
    def _build_row_hash(data_json: dict) -> str:
        normalized = json.dumps(
            data_json, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        )
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()

    def __repr__(self) -> str:
        return f"<DatasetRow id={self.id} row={self.row_number}>"
