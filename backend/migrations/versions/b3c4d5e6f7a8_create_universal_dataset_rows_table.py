"""create universal dataset row persistence table

Revision ID: b3c4d5e6f7a8
Revises: f9a1b2c3d4e5
Create Date: 2026-07-27 00:00:00.000000

Creates the universal dataset rows table for persisted dataset rows.
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "b3c4d5e6f7a8"
down_revision = "f9a1b2c3d4e5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "universal_dataset_rows",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("dataset_version_id", sa.UUID(), nullable=False),
        sa.Column("row_number", sa.Integer(), nullable=False),
        sa.Column("data_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("row_hash", sa.String(length=64), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["dataset_version_id"], ["universal_dataset_versions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("row_number > 0", name="ck_universal_dataset_rows_row_number_positive"),
        sa.UniqueConstraint("dataset_version_id", "row_number", name="uq_universal_dataset_rows_version_row_number"),
    )
    op.create_index("ix_universal_dataset_rows_dataset_version_id", "universal_dataset_rows", ["dataset_version_id"], unique=False)
    op.create_index(
        "ix_universal_dataset_rows_dataset_version_id_row_number",
        "universal_dataset_rows",
        ["dataset_version_id", "row_number"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_universal_dataset_rows_dataset_version_id_row_number", table_name="universal_dataset_rows")
    op.drop_index("ix_universal_dataset_rows_dataset_version_id", table_name="universal_dataset_rows")
    op.drop_table("universal_dataset_rows")
