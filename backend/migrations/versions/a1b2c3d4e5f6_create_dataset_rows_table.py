"""create dataset_rows table

Revision ID: a1b2c3d4e5f6
Revises: f3a4b5c6d7e8
Create Date: 2026-07-20 13:00:00.000000

Creates the dataset_rows table for storing approved ingestion row data.

Table: dataset_rows
  id                UUID PK
  ingestion_job_id  UUID FK → ingestion_jobs.id  ON DELETE CASCADE
  row_number        INTEGER NOT NULL  (zero-based)
  values            JSONB   NOT NULL  (must be a JSON object)
  created_at        TIMESTAMPTZ NOT NULL

Constraints:
  ck_dataset_rows_row_number_non_negative   row_number >= 0
  ck_dataset_rows_values_is_object          jsonb_typeof(values) = 'object'
  uq_dataset_rows_job_row_number            UNIQUE (ingestion_job_id, row_number)

Index:
  ix_dataset_rows_job_row_number            (ingestion_job_id, row_number)
  — covers both "all rows for job" and "specific row by number" queries.
  — no separate single-column index on ingestion_job_id is needed because
    the composite index covers it for left-prefix lookups.

Down migration drops the table; the index and constraints are dropped
automatically with the table.
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "a1b2c3d4e5f6"
down_revision = "f3a4b5c6d7e8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE dataset_rows (
            id                UUID         NOT NULL DEFAULT gen_random_uuid(),
            ingestion_job_id  UUID         NOT NULL,
            row_number        INTEGER      NOT NULL,
            values            JSONB        NOT NULL,
            created_at        TIMESTAMPTZ  NOT NULL DEFAULT now(),
            CONSTRAINT pk_dataset_rows
                PRIMARY KEY (id),
            CONSTRAINT fk_dataset_rows_ingestion_job
                FOREIGN KEY (ingestion_job_id)
                REFERENCES ingestion_jobs (id)
                ON DELETE CASCADE,
            CONSTRAINT ck_dataset_rows_row_number_non_negative
                CHECK (row_number >= 0),
            CONSTRAINT ck_dataset_rows_values_is_object
                CHECK (jsonb_typeof(values) = 'object'),
            CONSTRAINT uq_dataset_rows_job_row_number
                UNIQUE (ingestion_job_id, row_number)
        )
    """)
    op.create_index(
        "ix_dataset_rows_job_row_number",
        "dataset_rows",
        ["ingestion_job_id", "row_number"],
    )


def downgrade() -> None:
    op.drop_table("dataset_rows")
