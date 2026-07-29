"""create data_source_registry table

Revision ID: d1e2f3a4b5c6
Revises: c1d2e3f4a5b6
Create Date: 2025-07-22 09:00:00.000000

Creates the data_source_registry table which serves as the metadata
catalogue for all tracked datasets (official, organisational, internal).

Four PostgreSQL enum types are added:
    source_type_enum        OFFICIAL | ORGANIZATION | INTERNAL
    file_format_enum        CSV | XLSX | JSON | API | OTHER
    import_method_enum      MANUAL | SCHEDULED | API_PULL
    refresh_frequency_enum  DAILY | WEEKLY | MONTHLY | QUARTERLY | ANNUALLY | ADHOC
    verification_status_enum UNVERIFIED | PENDING | VERIFIED | REJECTED

Down migration:
    Drops the table and all four enum types.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "d1e2f3a4b5c6"
down_revision: Union[str, None] = "c1d2e3f4a5b6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── Enum types — create with IF NOT EXISTS ──────────────────────────
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE source_type_enum AS ENUM ('OFFICIAL', 'ORGANIZATION', 'INTERNAL');
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$;
    """)
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE file_format_enum AS ENUM ('CSV', 'XLSX', 'JSON', 'API', 'OTHER');
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$;
    """)
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE import_method_enum AS ENUM ('MANUAL', 'SCHEDULED', 'API_PULL');
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$;
    """)
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE refresh_frequency_enum AS ENUM ('DAILY', 'WEEKLY', 'MONTHLY', 'QUARTERLY', 'ANNUALLY', 'ADHOC');
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$;
    """)
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE verification_status_enum AS ENUM ('UNVERIFIED', 'PENDING', 'VERIFIED', 'REJECTED');
        EXCEPTION WHEN duplicate_object THEN NULL;
        END $$;
    """)

    # ── Table — use raw SQL to avoid SQLAlchemy re-creating enum types ──

    op.execute("""
        CREATE TABLE IF NOT EXISTS data_source_registry (
            id                  UUID         NOT NULL DEFAULT gen_random_uuid(),
            dataset_name        VARCHAR(255) NOT NULL,
            description         TEXT,
            publisher           VARCHAR(255),
            source_type         source_type_enum      NOT NULL,
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


def downgrade() -> None:
    op.drop_index("ix_data_source_registry_dataset_name",
                  table_name="data_source_registry")
    op.drop_constraint("uq_data_source_registry_dataset_name",
                       "data_source_registry", type_="unique")
    op.drop_table("data_source_registry")

    # Drop enum types in reverse creation order
    op.execute("DROP TYPE IF EXISTS verification_status_enum")
    op.execute("DROP TYPE IF EXISTS refresh_frequency_enum")
    op.execute("DROP TYPE IF EXISTS import_method_enum")
    op.execute("DROP TYPE IF EXISTS file_format_enum")
    op.execute("DROP TYPE IF EXISTS source_type_enum")
