"""split data_source_registry into data_sources and dataset_registry

Revision ID: e2f3a4b5c6d7
Revises: d1e2f3a4b5c6
Create Date: 2025-07-22 12:00:00.000000

Drops the combined data_source_registry table and replaces it with:
  data_sources       — publishing organisations / data origins
  dataset_registry   — individual datasets (FK → data_sources.id)

Enum types (source_type_enum, file_format_enum, import_method_enum,
refresh_frequency_enum, verification_status_enum) were created by the
previous migration and are reused here.

Down migration reverses: recreates data_source_registry, drops
dataset_registry and data_sources.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e2f3a4b5c6d7"
down_revision: Union[str, None] = "d1e2f3a4b5c6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Drop the old combined table (no data to preserve; foundation task only)
    op.execute("DROP TABLE IF EXISTS data_source_registry CASCADE")

    # ── data_sources ─────────────────────────────────────────────────────
    op.execute("""
        CREATE TABLE data_sources (
            id               UUID        NOT NULL DEFAULT gen_random_uuid(),
            name             VARCHAR(255) NOT NULL,
            description      TEXT,
            organization_type VARCHAR(100),
            base_url         VARCHAR(1000),
            country          VARCHAR(100),
            is_active        BOOLEAN      NOT NULL DEFAULT true,
            created_at       TIMESTAMPTZ  NOT NULL DEFAULT now(),
            updated_at       TIMESTAMPTZ  NOT NULL DEFAULT now(),
            CONSTRAINT pk_data_sources PRIMARY KEY (id),
            CONSTRAINT uq_data_sources_name UNIQUE (name)
        )
    """)
    op.create_index("ix_data_sources_name", "data_sources", ["name"])

    # ── dataset_registry ─────────────────────────────────────────────────
    op.execute("""
        CREATE TABLE dataset_registry (
            id                  UUID         NOT NULL DEFAULT gen_random_uuid(),
            data_source_id      UUID         NOT NULL,
            dataset_name        VARCHAR(255) NOT NULL,
            description         TEXT,
            source_type         source_type_enum       NOT NULL,
            category            VARCHAR(100),
            file_format         file_format_enum,
            source_url          VARCHAR(1000),
            publication_date    DATE,
            licence             VARCHAR(200),
            version             VARCHAR(100),
            import_method       import_method_enum,
            refresh_frequency   refresh_frequency_enum,
            last_imported_at    TIMESTAMPTZ,
            verification_status verification_status_enum NOT NULL DEFAULT 'UNVERIFIED',
            created_at          TIMESTAMPTZ  NOT NULL DEFAULT now(),
            updated_at          TIMESTAMPTZ  NOT NULL DEFAULT now(),
            CONSTRAINT pk_dataset_registry PRIMARY KEY (id),
            CONSTRAINT uq_dataset_registry_dataset_name UNIQUE (dataset_name),
            CONSTRAINT fk_dataset_registry_data_source
                FOREIGN KEY (data_source_id)
                REFERENCES data_sources (id)
                ON DELETE RESTRICT
        )
    """)
    op.create_index(
        "ix_dataset_registry_dataset_name", "dataset_registry", ["dataset_name"]
    )
    op.create_index(
        "ix_dataset_registry_data_source_id", "dataset_registry", ["data_source_id"]
    )


def downgrade() -> None:
    # Remove the two new tables
    op.execute("DROP TABLE IF EXISTS dataset_registry CASCADE")
    op.execute("DROP TABLE IF EXISTS data_sources CASCADE")

    # Recreate the old combined table
    op.execute("""
        CREATE TABLE data_source_registry (
            id                  UUID         NOT NULL DEFAULT gen_random_uuid(),
            dataset_name        VARCHAR(255) NOT NULL,
            description         TEXT,
            publisher           VARCHAR(255),
            source_type         source_type_enum       NOT NULL,
            category            VARCHAR(100),
            file_format         file_format_enum,
            source_url          VARCHAR(1000),
            publication_date    DATE,
            licence             VARCHAR(200),
            version             VARCHAR(100),
            import_method       import_method_enum,
            refresh_frequency   refresh_frequency_enum,
            last_imported_at    TIMESTAMPTZ,
            verification_status verification_status_enum NOT NULL DEFAULT 'UNVERIFIED',
            created_at          TIMESTAMPTZ  NOT NULL DEFAULT now(),
            updated_at          TIMESTAMPTZ  NOT NULL DEFAULT now(),
            CONSTRAINT pk_data_source_registry PRIMARY KEY (id),
            CONSTRAINT uq_data_source_registry_dataset_name UNIQUE (dataset_name)
        )
    """)
    op.create_index(
        "ix_data_source_registry_dataset_name",
        "data_source_registry",
        ["dataset_name"],
    )
