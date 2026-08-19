"""create import_templates table

Revision ID: 0a1b2c3d4e5f
Revises: f3a4b5c6d7e8
Create Date: 2026-07-25 12:00:00.000000
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0a1b2c3d4e5f"
down_revision = "f3a4b5c6d7e8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "import_templates",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            nullable=False,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "owner_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(length=200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "source_format",
            sa.String(length=50),
            nullable=False,
            server_default="csv",
        ),
        sa.Column("mapping_config", postgresql.JSONB(), nullable=False),
        sa.Column("original_headers", postgresql.JSONB(), nullable=False),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "owner_id",
            "name",
            name="uix_import_templates_owner_name",
        ),
    )
    op.create_index(
        "ix_import_templates_owner_id",
        "import_templates",
        ["owner_id"],
    )
    op.create_index(
        "ix_import_templates_owner_active",
        "import_templates",
        ["owner_id", "is_active"],
    )
    op.create_index(
        "ix_import_templates_name",
        "import_templates",
        ["name"],
    )


def downgrade() -> None:
    op.drop_index("ix_import_templates_name", table_name="import_templates")
    op.drop_index("ix_import_templates_owner_active", table_name="import_templates")
    op.drop_index("ix_import_templates_owner_id", table_name="import_templates")
    op.drop_table("import_templates")
