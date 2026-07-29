"""merge heads: unify divergent migration branches

Revision ID: c9d8e7f6a5b4
Revises: 0a1b2c3d4e5f, b3c4d5e6f7a8
Create Date: 2026-07-27 00:30:00.000000

This is a pure merge migration that records both existing heads as
parents. No schema operations are performed here; it simply unifies the
migration graph so `alembic upgrade head` can target a single head.
"""
from __future__ import annotations

from alembic import op


revision = "c9d8e7f6a5b4"
down_revision = ("0a1b2c3d4e5f", "b3c4d5e6f7a8")
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Merge-only migration: no schema changes.
    return None


def downgrade() -> None:
    # Downgrade would reintroduce multiple heads; not implemented.
    return None
