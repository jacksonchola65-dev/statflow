"""
models/import_template.py
=========================
ImportTemplate — reusable data import mapping configurations.

Ownership
---------
Every template belongs to a User (owner). The owner_id is NOT NULL and
cascades on delete (if the user is deleted, templates are too).

Uniqueness
----------
The (owner_id, name) pair is unique: one owner cannot have two templates
with the same name. Different owners may reuse names.

Mapping Configuration
---------------------
mapping_config is stored as JSONB and must conform to the
app.schemas.ingestion_mapping.MappingConfiguration schema.
The database stores raw JSON; application code validates via Pydantic.

Original Headers
----------------
original_headers stores the source CSV header list as JSON.
Preserved for reference and audit purposes.

Activity
--------
is_active defaults to True. Set to False to soft-disable a template
without deleting it. Future filtering may support disabled templates.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Optional

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.user import User


class ImportTemplate(Base):
    """Reusable data import mapping configuration owned by a user."""

    __tablename__ = "import_templates"

    __table_args__ = (
        UniqueConstraint(
            "owner_id",
            "name",
            name="uix_import_templates_owner_name",
        ),
        Index(
            "ix_import_templates_owner_active",
            "owner_id",
            "is_active",
        ),
    )

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

    name: Mapped[str] = mapped_column(
        String(200),
        nullable=False,
        index=True,
    )

    description: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )

    source_format: Mapped[str] = mapped_column(
        String(50),
        nullable=False,
        server_default="csv",
        default="csv",
    )

    # JSONB storage of MappingConfiguration schema (application-validated)
    mapping_config: Mapped[dict] = mapped_column(
        JSONB,
        nullable=False,
        comment=(
            "JSONB storage of MappingConfiguration. "
            "Must conform to app.schemas.ingestion_mapping.MappingConfiguration."
        ),
    )

    # Preserved original CSV headers from source file
    original_headers: Mapped[list[str]] = mapped_column(
        JSONB,
        nullable=False,
        comment=(
            "Original CSV header row (list of column names) "
            "for reference and audit purposes."
        ),
    )

    is_active: Mapped[bool] = mapped_column(
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
    owner: Mapped[User] = relationship(
        "User",
        back_populates="import_templates",
        foreign_keys=[owner_id],
    )

    def __repr__(self) -> str:
        return (
            f"<ImportTemplate id={self.id} "
            f"owner_id={self.owner_id} name={self.name!r}>"
        )
