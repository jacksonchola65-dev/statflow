import uuid
from datetime import datetime
from typing import TYPE_CHECKING, List

from app.db.base import Base
from sqlalchemy import DateTime, String, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

if TYPE_CHECKING:
    from app.models.data_point import DataPoint
    from app.models.district import District


class Province(Base):
    __tablename__ = "provinces"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    code: Mapped[str] = mapped_column(
        String(10),
        unique=True,
        index=True,
        nullable=False,
    )
    name: Mapped[str] = mapped_column(
        String(100),
        unique=True,
        index=True,
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )

    # Relationships
    districts: Mapped[List["District"]] = relationship(
        "District",
        back_populates="province",
        cascade="all, delete-orphan",
    )
    data_points: Mapped[List["DataPoint"]] = relationship(
        "DataPoint",
        back_populates="province",
    )

    def __repr__(self) -> str:
        return f"<Province code={self.code!r} name={self.name!r}>"
