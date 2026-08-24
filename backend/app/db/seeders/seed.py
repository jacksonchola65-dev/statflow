"""
Main seeder entry point.

Run with:
    python -m app.db.seeders.seed
"""

import asyncio
import logging
import sys

from app.core.config import normalize_async_database_url, settings
from app.db.seeders.categories import seed_categories
from app.db.seeders.data_points import seed_demo_data_points
from app.db.seeders.datasets import seed_datasets
from app.db.seeders.districts import seed_luapula_districts
from app.db.seeders.indicators import seed_indicators
from app.db.seeders.provinces import seed_provinces
from sqlalchemy.ext.asyncio import AsyncSession

logging.basicConfig(
    level=logging.WARNING,
    format="%(levelname)s: %(message)s",
)
# Suppress SQLAlchemy query echo during seeding
logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)


def _make_quiet_session_factory():
    """Create a session factory with echo disabled, regardless of ENVIRONMENT."""
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    quiet_engine = create_async_engine(
        normalize_async_database_url(settings.DATABASE_URL),
        echo=False,
        future=True,
        pool_pre_ping=True,
    )
    return async_sessionmaker(
        bind=quiet_engine,
        expire_on_commit=False,
        autocommit=False,
        autoflush=False,
    )


_SeedSession = _make_quiet_session_factory()


async def run_all_seeders(session: AsyncSession) -> None:
    """Execute all seeders in dependency order."""
    # ── Provinces ──────────────────────────────────────────
    province_result = await seed_provinces(session)
    print(
        f"  Provinces  "
        f"✔ created: {province_result['created']}  "
        f"✔ updated: {province_result['updated']}  "
        f"✔ total: {province_result['total']}"
    )

    # ── Districts ──────────────────────────────────────────
    district_result = await seed_luapula_districts(session)
    print(
        f"  Districts  "
        f"✔ created: {district_result['created']}  "
        f"✔ updated: {district_result['updated']}  "
        f"✔ total: {district_result['total']}"
    )

    # ── Categories ─────────────────────────────────────────
    category_result = await seed_categories(session)
    print(
        f"  Categories "
        f"✔ created: {category_result['created']}  "
        f"✔ updated: {category_result['updated']}  "
        f"✔ total: {category_result['total']}"
    )

    # ── Indicators ─────────────────────────────────────────
    indicator_result = await seed_indicators(session)
    print(
        f"  Indicators "
        f"✔ created: {indicator_result['created']}  "
        f"✔ updated: {indicator_result['updated']}  "
        f"✔ total: {indicator_result['total']}"
    )

    # ── Datasets ───────────────────────────────────────────
    dataset_result = await seed_datasets(session)
    print(
        f"  Datasets   "
        f"✔ created: {dataset_result['created']}  "
        f"✔ updated: {dataset_result['updated']}  "
        f"✔ total: {dataset_result['total']}"
    )

    # ── Data Points ────────────────────────────────────────
    dp_result = await seed_demo_data_points(session)
    print(
        f"  DataPoints "
        f"✔ created: {dp_result['created']}  "
        f"✔ updated: {dp_result['updated']}  "
        f"✔ total: {dp_result['total']}"
    )


async def main() -> None:
    print("\n StatFlow Database Seeder")
    print(" ─────────────────────────")

    try:
        async with _SeedSession() as session:
            await run_all_seeders(session)
    except Exception as exc:
        print(f"\n✘ Seeding failed: {exc}", file=sys.stderr)
        sys.exit(1)

    print(" ─────────────────────────")
    print(" Done.\n")


if __name__ == "__main__":
    asyncio.run(main())
