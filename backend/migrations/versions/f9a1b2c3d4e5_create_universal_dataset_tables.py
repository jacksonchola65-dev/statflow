"""create universal dataset persistence tables

Revision ID: f9a1b2c3d4e5
Revises: 19e8b7d4c2f1
Create Date: 2026-07-27 00:00:00.000000

Creates the universal dataset tables for persisted datasets, versions, and columns.
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "f9a1b2c3d4e5"
down_revision = "19e8b7d4c2f1"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create datasets table first so versions can reference it
    op.create_table(
        "universal_datasets",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("owner_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("source_filename", sa.String(length=500), nullable=False),
        sa.Column("status", sa.String(length=50), server_default=sa.text("'draft'"), nullable=False),
        sa.Column("current_version_id", sa.UUID(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_universal_datasets_owner_id", "universal_datasets", ["owner_id"], unique=False)
    op.create_index("ix_universal_datasets_name", "universal_datasets", ["name"], unique=False)

    # Create versions table after datasets so FK(dataset_id) is valid
    op.create_table(
        "universal_dataset_versions",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("dataset_id", sa.UUID(), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("row_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("column_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("schema_json", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("source_type", sa.String(length=50), server_default=sa.text("'csv'"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["dataset_id"], ["universal_datasets.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("dataset_id", "version_number", name="uq_universal_dataset_versions_dataset_version"),
    )
    op.create_index("ix_universal_dataset_versions_dataset_id", "universal_dataset_versions", ["dataset_id"], unique=False)

    op.create_table(
        "universal_dataset_columns",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("dataset_version_id", sa.UUID(), nullable=False),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("original_name", sa.String(length=500), nullable=False),
        sa.Column("inferred_type", sa.String(length=50), nullable=False),
        sa.Column("semantic_type", sa.String(length=100), nullable=True),
        sa.Column("ordinal_position", sa.Integer(), nullable=False),
        sa.Column("nullable", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.ForeignKeyConstraint(["dataset_version_id"], ["universal_dataset_versions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("dataset_version_id", "name", name="uq_universal_dataset_columns_version_name"),
    )
    op.create_index("ix_universal_dataset_columns_dataset_version_id", "universal_dataset_columns", ["dataset_version_id"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_universal_dataset_columns_dataset_version_id", table_name="universal_dataset_columns")
    op.drop_table("universal_dataset_columns")
    op.drop_index("ix_universal_dataset_versions_dataset_id", table_name="universal_dataset_versions")
    op.drop_table("universal_dataset_versions")
    op.drop_index("ix_universal_datasets_current_version_id", table_name="universal_datasets")
    op.drop_index("ix_universal_datasets_name", table_name="universal_datasets")
    op.drop_index("ix_universal_datasets_owner_id", table_name="universal_datasets")
    op.drop_table("universal_datasets")
