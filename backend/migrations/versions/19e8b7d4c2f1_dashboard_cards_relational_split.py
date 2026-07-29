"""split dashboard JSON cards into relational dashboard_cards table

Revision ID: 19e8b7d4c2f1
Revises: c7f8a9b0d1e2
Create Date: 2026-07-23 01:00:00.000000

Creates the approved two-table relational dashboard schema so card ordering,
ownership, and visualization snapshots are stored separately from dashboard
metadata.
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "19e8b7d4c2f1"
down_revision = "c7f8a9b0d1e2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("dashboards", sa.Column("owner_id", sa.UUID(), nullable=True))
    op.execute(sa.text("UPDATE dashboards SET owner_id = user_id"))
    op.alter_column("dashboards", "owner_id", nullable=False)

    op.create_table(
        "dashboard_cards",
        sa.Column("id", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("dashboard_id", sa.UUID(), nullable=False),
        sa.Column("title", sa.String(length=120), nullable=False),
        sa.Column("subtitle", sa.Text(), nullable=True),
        sa.Column("visualization_type", sa.String(length=20), nullable=False),
        sa.Column("visualization_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("size", sa.String(length=20), nullable=False, server_default="medium"),
        sa.Column("display_order", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["dashboard_id"], ["dashboards.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("display_order >= 0", name="ck_dashboard_cards_display_order_non_negative"),
        sa.UniqueConstraint("dashboard_id", "display_order", name="uq_dashboard_cards_dashboard_display_order"),
    )
    op.create_index("ix_dashboard_cards_dashboard_id", "dashboard_cards", ["dashboard_id"], unique=False)
    op.create_index("ix_dashboard_cards_dashboard_id_display_order", "dashboard_cards", ["dashboard_id", "display_order"], unique=False)

    op.execute(sa.text(
        """
        INSERT INTO dashboard_cards (
            id,
            dashboard_id,
            title,
            subtitle,
            visualization_type,
            visualization_snapshot,
            size,
            display_order,
            created_at,
            updated_at
        )
        SELECT
            gen_random_uuid(),
            d.id,
            COALESCE(card->>'title', 'Visualization card'),
            card->>'subtitle',
            COALESCE(NULLIF(card->>'visualization_type', ''), 'bar'),
            COALESCE(card->'visualization_snapshot', '{}'::jsonb),
            COALESCE(NULLIF(card->>'size', ''), 'medium'),
            COALESCE((card->>'order')::int, 0),
            now(),
            now()
        FROM dashboards AS d
        CROSS JOIN LATERAL jsonb_array_elements(COALESCE(d.cards::jsonb, '[]'::jsonb)) AS card
        """
    ))

    op.drop_index("ix_dashboards_user_id_updated_at", table_name="dashboards")
    op.drop_index("ix_dashboards_user_id_created_at", table_name="dashboards")
    op.drop_index("ix_dashboards_user_id", table_name="dashboards")

    op.drop_constraint("dashboards_user_id_fkey", "dashboards", type_="foreignkey")
    op.drop_column("dashboards", "user_id")
    op.create_foreign_key(
        "fk_dashboards_owner_id_users",
        "dashboards",
        "users",
        ["owner_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_index("ix_dashboards_owner_id", "dashboards", ["owner_id"], unique=False)
    op.create_index("ix_dashboards_owner_id_created_at", "dashboards", ["owner_id", "created_at"], unique=False)
    op.create_index("ix_dashboards_owner_id_updated_at", "dashboards", ["owner_id", "updated_at"], unique=False)
    op.drop_column("dashboards", "cards")


def downgrade() -> None:
    op.add_column("dashboards", sa.Column("cards", postgresql.JSONB(astext_type=sa.Text()), nullable=True, server_default=sa.text("'[]'::jsonb")))
    op.add_column("dashboards", sa.Column("user_id", sa.UUID(), nullable=True))
    op.execute(sa.text("UPDATE dashboards SET user_id = owner_id"))
    op.alter_column("dashboards", "user_id", nullable=False)

    op.execute(sa.text(
        """
        UPDATE dashboards AS d
        SET cards = (
            SELECT COALESCE(jsonb_agg(
                jsonb_build_object(
                    'id', dc.id,
                    'title', dc.title,
                    'subtitle', dc.subtitle,
                    'visualization_type', dc.visualization_type,
                    'visualization_snapshot', dc.visualization_snapshot,
                    'size', dc.size,
                    'order', dc.display_order
                )
                ORDER BY dc.display_order, dc.id
            ), '[]'::jsonb)
            FROM dashboard_cards AS dc
            WHERE dc.dashboard_id = d.id
        )
        """
    ))

    op.drop_constraint("fk_dashboards_owner_id_users", "dashboards", type_="foreignkey")
    op.drop_index("ix_dashboards_owner_id_updated_at", table_name="dashboards")
    op.drop_index("ix_dashboards_owner_id_created_at", table_name="dashboards")
    op.drop_index("ix_dashboards_owner_id", table_name="dashboards")
    op.drop_column("dashboards", "owner_id")

    op.drop_index("ix_dashboard_cards_dashboard_id_display_order", table_name="dashboard_cards")
    op.drop_index("ix_dashboard_cards_dashboard_id", table_name="dashboard_cards")
    op.drop_constraint("uq_dashboard_cards_dashboard_display_order", "dashboard_cards", type_="unique")
    op.drop_constraint("ck_dashboard_cards_display_order_non_negative", "dashboard_cards", type_="check")
    op.drop_table("dashboard_cards")

    op.create_index("ix_dashboards_user_id", "dashboards", ["user_id"], unique=False)
    op.create_index("ix_dashboards_user_id_created_at", "dashboards", ["user_id", "created_at"], unique=False)
    op.create_index("ix_dashboards_user_id_updated_at", "dashboards", ["user_id", "updated_at"], unique=False)
    op.create_foreign_key(
        "dashboards_user_id_fkey",
        "dashboards",
        "users",
        ["user_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.alter_column("dashboards", "cards", nullable=False, server_default=sa.text("'[]'::jsonb"))
