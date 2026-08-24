import asyncio
from logging.config import fileConfig

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection

# ---------------------------------------------------------------------------
# Alembic config object — gives access to values in alembic.ini
# ---------------------------------------------------------------------------
config = context.config

# Set up Python logging from alembic.ini
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# ---------------------------------------------------------------------------
# Pull DATABASE_URL from our application settings (reads backend/.env)
# This is the single source of truth — alembic.ini sqlalchemy.url is blank.
# ---------------------------------------------------------------------------
from app.core.config import normalize_sync_database_url, settings  # noqa: E402

config.set_main_option("sqlalchemy.url", normalize_sync_database_url(settings.DATABASE_URL))

# ---------------------------------------------------------------------------
# Import Base metadata so autogenerate can detect model changes.
# Individual model modules must be imported somewhere so their tables are
# registered on Base.metadata — app/models/__init__.py is the right place.
# ---------------------------------------------------------------------------
import app.models  # noqa: E402, F401  — ensures all models are registered
from app.db.base import Base  # noqa: E402

target_metadata = Base.metadata


# ---------------------------------------------------------------------------
# Offline mode — generates SQL without a live DB connection
# ---------------------------------------------------------------------------

def run_migrations_offline() -> None:
    """Emit migration SQL to stdout without connecting to the database."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        # Render as PostgreSQL-compatible SQL
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


# ---------------------------------------------------------------------------
# Online mode — runs migrations against a live DB connection
# Alembic uses a synchronous connection internally, so we convert the
# asyncpg URL to psycopg2 for the migration runner only.
# ---------------------------------------------------------------------------

def do_run_migrations(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Create an async engine and run migrations via a sync connection."""
    # Alembic cannot use asyncpg directly — we swap the driver to psycopg2
    # for migration execution only. The application runtime still uses asyncpg.
    sync_url = normalize_sync_database_url(settings.DATABASE_URL)

    from sqlalchemy import create_engine  # noqa: E402

    sync_engine = create_engine(sync_url, poolclass=pool.NullPool)
    with sync_engine.connect() as connection:
        do_run_migrations(connection)
    sync_engine.dispose()


def run_migrations_online() -> None:
    """Entry point for online migration mode."""
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
