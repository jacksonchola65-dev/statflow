import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING, List, Optional

from app.db.base import Base
from sqlalchemy import Boolean, DateTime, Integer, String, Text, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

if TYPE_CHECKING:
    from app.models.data_point import DataPoint


class Dataset(Base):
    __tablename__ = "datasets"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    name: Mapped[str] = mapped_column(
        String(150),
        nullable=False,
    )
    description: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )
    source_name: Mapped[Optional[str]] = mapped_column(
        String(150),
        nullable=True,
    )
    source_url: Mapped[Optional[str]] = mapped_column(
        String(500),
        nullable=True,
    )
    reference_year: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
    )
    is_published: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=text("false"),
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

    # Relationships
    data_points: Mapped[List["DataPoint"]] = relationship(
        "DataPoint",
        back_populates="dataset",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<Dataset id={self.id} name={self.name!r}>"
