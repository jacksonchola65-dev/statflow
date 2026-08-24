"""Production-safe bootstrap for canonical reference data only."""

import asyncio
import sys

from app.core.config import normalize_async_database_url, settings
from app.db.seeders.categories import STATFLOW_CATEGORIES, seed_categories
from app.db.seeders.districts import LUAPULA_DISTRICTS, seed_luapula_districts
from app.db.seeders.indicators import STATFLOW_INDICATORS, seed_indicators
from app.db.seeders.provinces import ZAMBIA_PROVINCES, seed_provinces
from app.models.category import Category
from app.models.district import District
from app.models.indicator import Indicator
from app.models.province import Province
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine


class ReferenceDataConflictError(RuntimeError):
    """Raised when existing reference data disagrees with canonical definitions."""


async def validate_reference_data(session: AsyncSession) -> None:
    """Validate existing canonical rows before any reference seeder writes."""
    conflicts: list[str] = []
    categories = {
        row.code: row for row in (await session.execute(select(Category))).scalars().all()
    }
    for record in STATFLOW_CATEGORIES:
        existing = categories.get(record.code)
        if existing and (existing.name, existing.description) != (
            record.name,
            record.description,
        ):
            conflicts.append(f"category {record.code}")

    provinces = {row.code: row for row in (await session.execute(select(Province))).scalars().all()}
    for record in ZAMBIA_PROVINCES:
        existing = provinces.get(record.code)
        if existing and existing.name != record.name:
            conflicts.append(f"province {record.code}")

    districts = {row.code: row for row in (await session.execute(select(District))).scalars().all()}
    for record in LUAPULA_DISTRICTS:
        existing = districts.get(record.code)
        luapula = provinces.get("LP")
        if existing and (
            existing.name != record.name or luapula is None or existing.province_id != luapula.id
        ):
            conflicts.append(f"district {record.code}")

    indicators = {
        row.code: row for row in (await session.execute(select(Indicator))).scalars().all()
    }
    for record in STATFLOW_INDICATORS:
        existing = indicators.get(record.code)
        category = categories.get(record.category_code)
        if existing and (
            existing.name != record.name
            or existing.description != record.description
            or existing.unit != record.unit
            or existing.source_name != record.source_name
            or category is None
            or existing.category_id != category.id
        ):
            conflicts.append(f"indicator {record.code}")

    if conflicts:
        raise ReferenceDataConflictError(
            "Canonical reference data conflicts detected: " + ", ".join(conflicts)
        )


async def bootstrap_reference_data(session: AsyncSession) -> None:
    """Seed only categories, provinces, Luapula districts, and indicators."""
    await validate_reference_data(session)
    await seed_categories(session)
    await seed_provinces(session)
    await seed_luapula_districts(session)
    await seed_indicators(session)


async def main() -> None:
    engine = create_async_engine(
        normalize_async_database_url(settings.DATABASE_URL),
        echo=False,
        future=True,
        pool_pre_ping=True,
    )
    factory = async_sessionmaker(
        bind=engine,
        expire_on_commit=False,
        autocommit=False,
        autoflush=False,
    )
    try:
        async with factory() as session:
            await bootstrap_reference_data(session)
        print("Reference data bootstrap completed: categories, provinces, districts, indicators")
    except Exception as exc:
        print(f"Reference data bootstrap failed: {exc}", file=sys.stderr)
        raise
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
