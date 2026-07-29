"""create dashboards table

Revision ID: c7f8a9b0d1e2
Revises: f3a4b5c6d7e8
Create Date: 2026-07-23 00:00:00.000000

Creates the persisted dashboard table for user-owned analytics workspaces.
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "c7f8a9b0d1e2"
down_revision = "b2c3d4e5f6a7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "dashboards",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("title", sa.String(length=120), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("cards", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_dashboards_user_id", "dashboards", ["user_id"], unique=False)
    op.create_index("ix_dashboards_user_id_created_at", "dashboards", ["user_id", "created_at"], unique=False)
    op.create_index("ix_dashboards_user_id_updated_at", "dashboards", ["user_id", "updated_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_dashboards_user_id_updated_at", table_name="dashboards")
    op.drop_index("ix_dashboards_user_id_created_at", table_name="dashboards")
    op.drop_index("ix_dashboards_user_id", table_name="dashboards")
    op.drop_table("dashboards")
