"""create ingestion_jobs and dataset_columns tables

Revision ID: f3a4b5c6d7e8
Revises: e2f3a4b5c6d7
Create Date: 2026-07-20 12:00:00.000000

Creates the ingestion pipeline tables:
  ingestion_jobs    — tracks file-inspection runs per DatasetRegistry entry
  dataset_columns   — per-column metadata produced during inspection

New PostgreSQL enum types:
  ingestion_status_enum        (PENDING, PROCESSING, COMPLETED, FAILED)
  inferred_column_type_enum    (INTEGER, DECIMAL, BOOLEAN, DATE, DATETIME, TEXT)

Reuses the existing file_format_enum from data_sources.

ordinal_position (zero-based) is included from the start to record the
left-to-right position of each column in the original source file.

Constraints on dataset_columns:
  ck_dataset_columns_ordinal_position_non_negative  ordinal_position >= 0
  ck_dataset_columns_original_name_not_empty        length(original_name) > 0
  ck_dataset_columns_normalized_name_not_empty      length(normalized_name) > 0
  ck_dataset_columns_missing_count_non_negative     missing_count >= 0
  ck_dataset_columns_unique_count_non_negative      unique_count >= 0
  uq_dataset_columns_job_normalized_name            UNIQUE(ingestion_job_id, normalized_name)
  uq_dataset_columns_job_ordinal_position           UNIQUE(ingestion_job_id, ordinal_position)

Constraints on ingestion_jobs:
  ck_ingestion_jobs_file_size_bytes_non_negative    file_size_bytes >= 0
  ck_ingestion_jobs_row_count_non_negative          row_count >= 0
  ck_ingestion_jobs_column_count_non_negative       column_count >= 0

Down migration drops both tables and both new enum types.
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "f3a4b5c6d7e8"
down_revision = "e2f3a4b5c6d7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── New enum types ────────────────────────────────────────────────────
    op.execute("""
        CREATE TYPE ingestion_status_enum AS ENUM (
            'PENDING', 'PROCESSING', 'COMPLETED', 'FAILED'
        )
    """)
    op.execute("""
        CREATE TYPE inferred_column_type_enum AS ENUM (
            'INTEGER', 'DECIMAL', 'BOOLEAN', 'DATE', 'DATETIME', 'TEXT'
        )
    """)

    # ── ingestion_jobs ────────────────────────────────────────────────────
    op.execute("""
        CREATE TABLE ingestion_jobs (
            id                   UUID                  NOT NULL DEFAULT gen_random_uuid(),
            dataset_registry_id  UUID                  NOT NULL,
            status               ingestion_status_enum NOT NULL DEFAULT 'PENDING',
            original_filename    VARCHAR(500)          NOT NULL,
            stored_filename      VARCHAR(500),
            file_format          file_format_enum,
            file_size_bytes      BIGINT,
            row_count            INTEGER,
            column_count         INTEGER,
            started_at           TIMESTAMPTZ,
            completed_at         TIMESTAMPTZ,
            failed_at            TIMESTAMPTZ,
            error_message        TEXT,
            created_by_user_id   UUID,
            created_at           TIMESTAMPTZ           NOT NULL DEFAULT now(),
            updated_at           TIMESTAMPTZ           NOT NULL DEFAULT now(),
            CONSTRAINT pk_ingestion_jobs PRIMARY KEY (id),
            CONSTRAINT fk_ingestion_jobs_dataset_registry
                FOREIGN KEY (dataset_registry_id)
                REFERENCES dataset_registry (id)
                ON DELETE RESTRICT,
            CONSTRAINT fk_ingestion_jobs_user
                FOREIGN KEY (created_by_user_id)
                REFERENCES users (id)
                ON DELETE SET NULL,
            CONSTRAINT ck_ingestion_jobs_file_size_bytes_non_negative
                CHECK (file_size_bytes >= 0),
            CONSTRAINT ck_ingestion_jobs_row_count_non_negative
                CHECK (row_count >= 0),
            CONSTRAINT ck_ingestion_jobs_column_count_non_negative
                CHECK (column_count >= 0)
        )
    """)
    op.create_index("ix_ingestion_jobs_dataset_registry_id", "ingestion_jobs", ["dataset_registry_id"])
    op.create_index("ix_ingestion_jobs_created_by_user_id",  "ingestion_jobs", ["created_by_user_id"])
    op.create_index("ix_ingestion_jobs_status",              "ingestion_jobs", ["status"])
    op.create_index("ix_ingestion_jobs_created_at",          "ingestion_jobs", ["created_at"])

    # ── dataset_columns ───────────────────────────────────────────────────
    op.execute("""
        CREATE TABLE dataset_columns (
            id                UUID                       NOT NULL DEFAULT gen_random_uuid(),
            ingestion_job_id  UUID                       NOT NULL,
            ordinal_position  INTEGER                    NOT NULL,
            original_name     VARCHAR(500)               NOT NULL,
            normalized_name   VARCHAR(500)               NOT NULL,
            inferred_type     inferred_column_type_enum  NOT NULL DEFAULT 'TEXT',
            nullable          BOOLEAN                    NOT NULL DEFAULT false,
            missing_count     INTEGER                    NOT NULL DEFAULT 0,
            unique_count      INTEGER                    NOT NULL DEFAULT 0,
            sample_values     JSONB,
            created_at        TIMESTAMPTZ                NOT NULL DEFAULT now(),
            CONSTRAINT pk_dataset_columns PRIMARY KEY (id),
            CONSTRAINT fk_dataset_columns_job
                FOREIGN KEY (ingestion_job_id)
                REFERENCES ingestion_jobs (id)
                ON DELETE CASCADE,
            CONSTRAINT ck_dataset_columns_ordinal_position_non_negative
                CHECK (ordinal_position >= 0),
            CONSTRAINT ck_dataset_columns_original_name_not_empty
                CHECK (length(original_name) > 0),
            CONSTRAINT ck_dataset_columns_normalized_name_not_empty
                CHECK (length(normalized_name) > 0),
            CONSTRAINT ck_dataset_columns_missing_count_non_negative
                CHECK (missing_count >= 0),
            CONSTRAINT ck_dataset_columns_unique_count_non_negative
                CHECK (unique_count >= 0),
            CONSTRAINT uq_dataset_columns_job_normalized_name
                UNIQUE (ingestion_job_id, normalized_name),
            CONSTRAINT uq_dataset_columns_job_ordinal_position
                UNIQUE (ingestion_job_id, ordinal_position)
        )
    """)
    op.create_index("ix_dataset_columns_ingestion_job_id", "dataset_columns", ["ingestion_job_id"])


def downgrade() -> None:
    op.drop_table("dataset_columns")
    op.drop_table("ingestion_jobs")
    op.execute("DROP TYPE IF EXISTS inferred_column_type_enum")
    op.execute("DROP TYPE IF EXISTS ingestion_status_enum")
