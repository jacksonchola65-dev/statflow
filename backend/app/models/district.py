import uuid
from datetime import datetime
from typing import TYPE_CHECKING, List

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.data_point import DataPoint
    from app.models.province import Province


class District(Base):
    __tablename__ = "districts"

    __table_args__ = (
        UniqueConstraint("province_id", "code", name="uq_districts_province_code"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    province_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("provinces.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    code: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )

    # Relationships
    province: Mapped["Province"] = relationship(
        "Province",
        back_populates="districts",
    )
    data_points: Mapped[List["DataPoint"]] = relationship(
        "DataPoint",
        back_populates="district",
    )

    def __repr__(self) -> str:
        return f"<District code={self.code!r} name={self.name!r}>"
