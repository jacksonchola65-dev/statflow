import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.dataset import Dataset
    from app.models.district import District
    from app.models.indicator import Indicator
    from app.models.province import Province


class DataPoint(Base):
    __tablename__ = "data_points"

    __table_args__ = (
        # XOR: exactly one geographic level must be set
        CheckConstraint(
            "(province_id IS NOT NULL AND district_id IS NULL) OR "
            "(district_id IS NOT NULL AND province_id IS NULL)",
            name="ck_data_points_exactly_one_geo",
        ),
        # Partial unique index — province-level data points
        Index(
            "uix_data_points_province_level",
            "dataset_id",
            "indicator_id",
            "province_id",
            "reference_year",
            unique=True,
            postgresql_where=text("province_id IS NOT NULL AND district_id IS NULL"),
        ),
        # Partial unique index — district-level data points
        Index(
            "uix_data_points_district_level",
            "dataset_id",
            "indicator_id",
            "district_id",
            "reference_year",
            unique=True,
            postgresql_where=text("district_id IS NOT NULL AND province_id IS NULL"),
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
        ForeignKey("datasets.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    indicator_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("indicators.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    province_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("provinces.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    district_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("districts.id", ondelete="RESTRICT"),
        nullable=True,
        index=True,
    )
    value: Mapped[float] = mapped_column(
        Numeric(20, 4),
        nullable=False,
    )
    reference_year: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )

    # Relationships
    dataset: Mapped["Dataset"] = relationship(
        "Dataset",
        back_populates="data_points",
    )
    indicator: Mapped["Indicator"] = relationship(
        "Indicator",
        back_populates="data_points",
    )
    province: Mapped[Optional["Province"]] = relationship(
        "Province",
        back_populates="data_points",
    )
    district: Mapped[Optional["District"]] = relationship(
        "District",
        back_populates="data_points",
    )

    def __repr__(self) -> str:
        return (
            f"<DataPoint dataset={self.dataset_id} "
            f"indicator={self.indicator_id} year={self.reference_year}>"
        )
