"""add user role enum

Revision ID: c1d2e3f4a5b6
Revises: 6f3e7ff115e1
Create Date: 2025-07-15 12:00:00.000000

Upgrades the users table:
  - Creates the PostgreSQL enum type user_role
    (ADMIN, DATA_MANAGER, ANALYST, VIEWER)
  - Adds role column (NOT NULL, server default 'VIEWER')
  - Copies data: is_superuser=true → ADMIN, else → VIEWER
  - Drops the is_superuser column

Reversal:
  - Adds is_superuser column back (boolean, default false)
  - Copies data: role=ADMIN → is_superuser=true
  - Drops role column
  - Drops the user_role enum type
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = 'c1d2e3f4a5b6'
down_revision: Union[str, Sequence[str], None] = '6f3e7ff115e1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# The enum values in definition order
_ROLE_VALUES = ('ADMIN', 'DATA_MANAGER', 'ANALYST', 'VIEWER')

# Helper to check whether a column exists in a table (defensive)
def _column_exists(connection, table: str, column: str) -> bool:
    result = connection.execute(
        sa.text(
            "SELECT 1 FROM information_schema.columns "
            "WHERE table_name = :t AND column_name = :c"
        ),
        {"t": table, "c": column},
    )
    return result.fetchone() is not None


def upgrade() -> None:
    """
    1. Create the PostgreSQL user_role enum type.
    2. Add role column (nullable initially so we can back-fill).
    3. Copy data: set role='ADMIN' where is_superuser IS TRUE, else 'VIEWER'.
    4. Set NOT NULL on role column.
    5. Drop is_superuser column (if it exists).
    """
    bind = op.get_bind()

    # ── Step 1: Create the enum type ──────────────────────────────────────
    user_role_enum = postgresql.ENUM(*_ROLE_VALUES, name='user_role', create_type=False)
    user_role_enum.create(bind, checkfirst=True)

    # ── Step 2: Add role column as nullable (allows back-fill without a
    #    default forced on existing rows before we populate them) ─────────
    op.add_column(
        'users',
        sa.Column(
            'role',
            sa.Enum(*_ROLE_VALUES, name='user_role', create_type=False),
            nullable=True,
        ),
    )

    # ── Step 3: Copy data from is_superuser → role ───────────────────────
    if _column_exists(bind, 'users', 'is_superuser'):
        bind.execute(
            sa.text(
                "UPDATE users SET role = CASE "
                "  WHEN is_superuser = TRUE THEN 'ADMIN'::user_role "
                "  ELSE 'VIEWER'::user_role "
                "END"
            )
        )
    else:
        # is_superuser was never created; default everything to VIEWER
        bind.execute(sa.text("UPDATE users SET role = 'VIEWER'::user_role"))

    # ── Step 4: Add NOT NULL constraint and server default ────────────────
    op.alter_column('users', 'role', nullable=False,
                    server_default=sa.text("'VIEWER'"))

    # ── Step 5: Drop is_superuser if it exists ───────────────────────────
    if _column_exists(bind, 'users', 'is_superuser'):
        op.drop_column('users', 'is_superuser')


def downgrade() -> None:
    """
    1. Add is_superuser column (boolean, nullable initially).
    2. Copy data: role='ADMIN' → is_superuser=true, else false.
    3. Set NOT NULL on is_superuser with server default false.
    4. Drop role column.
    5. Drop the user_role enum type.
    """
    bind = op.get_bind()

    # ── Step 1: Add is_superuser column as nullable ───────────────────────
    op.add_column(
        'users',
        sa.Column(
            'is_superuser',
            sa.Boolean(),
            nullable=True,
        ),
    )

    # ── Step 2: Copy data from role → is_superuser ────────────────────────
    bind.execute(
        sa.text(
            "UPDATE users SET is_superuser = (role = 'ADMIN'::user_role)"
        )
    )

    # ── Step 3: Apply NOT NULL + server default ───────────────────────────
    op.alter_column(
        'users', 'is_superuser',
        nullable=False,
        server_default=sa.text('false'),
    )

    # ── Step 4: Drop role column ──────────────────────────────────────────
    op.drop_column('users', 'role')

    # ── Step 5: Drop the enum type ────────────────────────────────────────
    user_role_enum = postgresql.ENUM(*_ROLE_VALUES, name='user_role', create_type=False)
    user_role_enum.drop(bind, checkfirst=True)
