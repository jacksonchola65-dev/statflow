from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from app.db.base import Base
from sqlalchemy import DateTime, ForeignKey, Index, String, Text, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

if TYPE_CHECKING:
    from app.models.dashboard_card import DashboardCard
    from app.models.user import User


class Dashboard(Base):
    """User-owned saved dashboard composition with visualization snapshots."""

    __tablename__ = "dashboards"

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
    title: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    cards: Mapped[list["DashboardCard"]] = relationship(
        "DashboardCard",
        back_populates="dashboard",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="DashboardCard.display_order.asc()",
        lazy="select",
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
        Index("ix_dashboards_owner_id_created_at", "owner_id", "created_at"),
        Index("ix_dashboards_owner_id_updated_at", "owner_id", "updated_at"),
    )

    owner: Mapped["User"] = relationship(
        "User",
        back_populates="dashboards",
        foreign_keys=[owner_id],
        lazy="select",
    )

    def __repr__(self) -> str:
        return f"<Dashboard id={self.id} owner_id={self.owner_id} title={self.title!r}>"
