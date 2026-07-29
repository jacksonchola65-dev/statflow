"""drop redundant ix_dataset_rows_job_row_number index

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-07-20 14:00:00.000000

The previous migration (a1b2c3d4e5f6) created both:
  - uq_dataset_rows_job_row_number  UNIQUE (ingestion_job_id, row_number)
  - ix_dataset_rows_job_row_number  INDEX  (ingestion_job_id, row_number)

PostgreSQL automatically creates a B-tree index to back a UNIQUE constraint.
The explicit index is therefore an exact duplicate and increases write overhead
without providing any query-plan benefit.

This migration drops the redundant explicit index.
The unique constraint and its backing index remain.

Down migration recreates the redundant index (safe to roll back).
"""
from __future__ import annotations

from alembic import op


revision = "b2c3d4e5f6a7"
down_revision = "a1b2c3d4e5f6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_index("ix_dataset_rows_job_row_number", table_name="dataset_rows")


def downgrade() -> None:
    op.create_index(
        "ix_dataset_rows_job_row_number",
        "dataset_rows",
        ["ingestion_job_id", "row_number"],
    )
