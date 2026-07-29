import enum
import uuid
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Boolean, DateTime, Enum, String, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.dashboard import Dashboard
    from app.models.import_template import ImportTemplate
    from app.models.universal_dataset import UniversalDataset

from app.models.universal_dataset import UniversalDataset


class UserRole(str, enum.Enum):
    """Role assigned to every StatFlow user account."""
    ADMIN = "ADMIN"
    DATA_MANAGER = "DATA_MANAGER"
    ANALYST = "ANALYST"
    VIEWER = "VIEWER"


class User(Base):
    __tablename__ = "users"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
        server_default=text("gen_random_uuid()"),
    )
    email: Mapped[str] = mapped_column(
        String(255),
        unique=True,
        index=True,
        nullable=False,
    )
    hashed_password: Mapped[str] = mapped_column(
        String,
        nullable=False,
    )
    full_name: Mapped[Optional[str]] = mapped_column(
        String(255),
        nullable=True,
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        default=True,
        server_default=text("true"),
        nullable=False,
    )
    role: Mapped[UserRole] = mapped_column(
        Enum(
            UserRole,
            name="user_role",
            native_enum=True,
        ),
        nullable=False,
        default=UserRole.VIEWER,
        server_default=text("'VIEWER'"),
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

    dashboards: Mapped[list["Dashboard"]] = relationship(
        "Dashboard",
        back_populates="owner",
        cascade="all, delete-orphan",
        passive_deletes=True,
        lazy="select",
    )

    import_templates: Mapped[list["ImportTemplate"]] = relationship(
        "ImportTemplate",
        back_populates="owner",
        cascade="all, delete-orphan",
        passive_deletes=True,
        lazy="select",
    )

    universal_datasets: Mapped[list["UniversalDataset"]] = relationship(
        "UniversalDataset",
        back_populates="owner",
        cascade="all, delete-orphan",
        passive_deletes=True,
        lazy="select",
    )

    def __repr__(self) -> str:
        return f"<User id={self.id} email={self.email!r} role={self.role}>"
