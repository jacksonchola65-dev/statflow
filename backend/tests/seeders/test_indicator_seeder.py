"""
Tests for app.db.seeders.indicators.seed_indicators

Each test that runs the indicator seeder must ensure the required categories
exist. We re-seed categories at the start of each test and clean up both
indicators and any test-created categories at the end.
"""
import pytest
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.seeders.categories import seed_categories
from app.db.seeders.indicators import (
    REQUIRED_CATEGORY_CODES,
    STATFLOW_INDICATORS,
    CategoryNotFoundError,
    seed_indicators,
)
from app.models.category import Category
from app.models.indicator import Indicator


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

SEEDED_INDICATOR_CODES = [r.code for r in STATFLOW_INDICATORS]
SEEDED_CATEGORY_CODES = REQUIRED_CATEGORY_CODES


async def _ensure_categories(session: AsyncSession) -> None:
    """Ensure all required categories exist (idempotent)."""
    await seed_categories(session)


async def _delete_seeded_indicators(session: AsyncSession) -> None:
    await session.execute(
        delete(Indicator).where(Indicator.code.in_(SEEDED_INDICATOR_CODES))
    )
    await session.commit()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_first_run_creates_10_indicators(db_session: AsyncSession) -> None:
    await _ensure_categories(db_session)
    await _delete_seeded_indicators(db_session)

    result = await seed_indicators(db_session)

    assert result["created"] == len(STATFLOW_INDICATORS)
    assert result["updated"] == 0
    assert result["total"] == len(STATFLOW_INDICATORS)

    await _delete_seeded_indicators(db_session)


@pytest.mark.asyncio
async def test_second_run_creates_no_duplicates(db_session: AsyncSession) -> None:
    await _ensure_categories(db_session)
    await _delete_seeded_indicators(db_session)

    await seed_indicators(db_session)
    second = await seed_indicators(db_session)

    assert second["created"] == 0
    assert second["total"] == len(STATFLOW_INDICATORS)

    result = await db_session.execute(
        select(Indicator).where(Indicator.code.in_(SEEDED_INDICATOR_CODES))
    )
    assert len(result.scalars().all()) == len(STATFLOW_INDICATORS)

    await _delete_seeded_indicators(db_session)


@pytest.mark.asyncio
async def test_codes_are_unique_after_seeding(db_session: AsyncSession) -> None:
    await _ensure_categories(db_session)
    await _delete_seeded_indicators(db_session)
    await seed_indicators(db_session)

    result = await db_session.execute(
        select(Indicator).where(Indicator.code.in_(SEEDED_INDICATOR_CODES))
    )
    indicators = result.scalars().all()
    codes = [i.code for i in indicators]
    assert len(codes) == len(set(codes))

    await _delete_seeded_indicators(db_session)


@pytest.mark.asyncio
async def test_changed_field_is_updated(db_session: AsyncSession) -> None:
    await _ensure_categories(db_session)
    await _delete_seeded_indicators(db_session)
    await seed_indicators(db_session)

    result = await db_session.execute(
        select(Indicator).where(Indicator.code == "GDP_PER_CAPITA")
    )
    gdp = result.scalar_one()
    gdp.unit = "OLD_UNIT"
    await db_session.commit()

    update_result = await seed_indicators(db_session)
    assert update_result["updated"] >= 1

    result = await db_session.execute(
        select(Indicator).where(Indicator.code == "GDP_PER_CAPITA")
    )
    gdp_after = result.scalar_one()
    assert gdp_after.unit == "USD"

    await _delete_seeded_indicators(db_session)


@pytest.mark.asyncio
async def test_total_remains_10_after_repeated_runs(db_session: AsyncSession) -> None:
    await _ensure_categories(db_session)
    await _delete_seeded_indicators(db_session)

    for _ in range(3):
        result = await seed_indicators(db_session)
        assert result["total"] == len(STATFLOW_INDICATORS)

    result = await db_session.execute(
        select(Indicator).where(Indicator.code.in_(SEEDED_INDICATOR_CODES))
    )
    assert len(result.scalars().all()) == len(STATFLOW_INDICATORS)

    await _delete_seeded_indicators(db_session)


@pytest.mark.asyncio
async def test_missing_category_raises_clear_error(db_session: AsyncSession) -> None:
    """With no categories present at all, the seeder must raise clearly."""
    await _delete_seeded_indicators(db_session)

    # Delete all required categories temporarily
    await db_session.execute(
        delete(Category).where(Category.code.in_(SEEDED_CATEGORY_CODES))
    )
    await db_session.commit()

    with pytest.raises(CategoryNotFoundError) as exc_info:
        await seed_indicators(db_session)

    error_msg = str(exc_info.value)
    assert any(code in error_msg for code in SEEDED_CATEGORY_CODES)

    # Restore categories
    await seed_categories(db_session)
