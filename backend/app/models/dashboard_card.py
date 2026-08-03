from __future__ import annotations

import enum
import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Any

from app.db.base import Base
from sqlalchemy import (
    CheckConstraint,
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

if TYPE_CHECKING:
    from app.models.dashboard import Dashboard


class DashboardCardSize(str, enum.Enum):
    SMALL = "small"
    MEDIUM = "medium"
    LARGE = "large"


class DashboardVisualizationType(str, enum.Enum):
    KPI = "kpi"
    BAR = "bar"
    LINE = "line"
    AREA = "area"
    PIE = "pie"


class DashboardCard(Base):
    """Relational card entry stored under a user-owned dashboard."""

    __tablename__ = "dashboard_cards"

    id: Mapped[str] = mapped_column(
        String(120),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
        server_default=text("gen_random_uuid()::text"),
    )
    dashboard_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("dashboards.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    title: Mapped[str] = mapped_column(String(120), nullable=False)
    subtitle: Mapped[str | None] = mapped_column(Text, nullable=True)
    visualization_type: Mapped[DashboardVisualizationType] = mapped_column(
        String(20),
        nullable=False,
    )
    visualization_snapshot: Mapped[dict[str, Any]] = mapped_column(
        JSONB,
        nullable=False,
        default=dict,
        server_default=text("'{}'::jsonb"),
    )
    size: Mapped[DashboardCardSize] = mapped_column(
        String(20),
        nullable=False,
        default=DashboardCardSize.MEDIUM,
    )
    display_order: Mapped[int] = mapped_column(
        nullable=False,
        default=0,
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
        CheckConstraint("display_order >= 0", name="ck_dashboard_cards_display_order_non_negative"),
        UniqueConstraint(
            "dashboard_id", "display_order", name="uq_dashboard_cards_dashboard_display_order"
        ),
        Index("ix_dashboard_cards_dashboard_id_display_order", "dashboard_id", "display_order"),
    )

    dashboard: Mapped["Dashboard"] = relationship(
        "Dashboard",
        back_populates="cards",
        foreign_keys=[dashboard_id],
        lazy="select",
    )

    @property
    def order(self) -> int:
        return self.display_order

    @property
    def visualization_type_value(self) -> str:
        return (
            self.visualization_type.value
            if isinstance(self.visualization_type, DashboardVisualizationType)
            else str(self.visualization_type)
        )

    def __repr__(self) -> str:
        return f"<DashboardCard id={self.id} dashboard_id={self.dashboard_id} title={self.title!r}>"
