"""
Tests for app.db.seeders.categories.seed_categories

Each test cleans up the seeded categories afterwards to stay independent.
"""

import pytest
from app.db.seeders.categories import (
    STATFLOW_CATEGORIES,
    seed_categories,
)
from app.models.category import Category
from app.models.indicator import Indicator
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

SEEDED_CODES = [r.code for r in STATFLOW_CATEGORIES]


async def _delete_seeded_categories(session: AsyncSession) -> None:
    """
    Remove all categories inserted by the seeder.

    Indicators reference categories via FK, so any indicators that belong
    to the seeded categories must be removed first to avoid FK violations.
    This handles cases where indicators have been seeded by other test
    modules in the same session (e.g. test_imports.py).
    """
    # First remove any indicators belonging to these categories
    category_ids_result = await session.execute(
        select(Category.id).where(Category.code.in_(SEEDED_CODES))
    )
    category_ids = [row.id for row in category_ids_result.all()]
    if category_ids:
        await session.execute(delete(Indicator).where(Indicator.category_id.in_(category_ids)))
    # Now safe to delete categories
    await session.execute(delete(Category).where(Category.code.in_(SEEDED_CODES)))
    await session.commit()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_first_run_creates_10_categories(db_session: AsyncSession) -> None:
    await _delete_seeded_categories(db_session)

    result = await seed_categories(db_session)

    assert result["created"] == 10
    assert result["updated"] == 0
    assert result["total"] == 10

    await _delete_seeded_categories(db_session)


@pytest.mark.asyncio
async def test_second_run_creates_no_duplicates(db_session: AsyncSession) -> None:
    await _delete_seeded_categories(db_session)

    await seed_categories(db_session)
    second = await seed_categories(db_session)

    assert second["created"] == 0
    assert second["total"] == 10

    # Verify actual row count
    result = await db_session.execute(select(Category).where(Category.code.in_(SEEDED_CODES)))
    rows = result.scalars().all()
    assert len(rows) == 10

    await _delete_seeded_categories(db_session)


@pytest.mark.asyncio
async def test_codes_are_unique(db_session: AsyncSession) -> None:
    await _delete_seeded_categories(db_session)
    await seed_categories(db_session)

    result = await db_session.execute(select(Category).where(Category.code.in_(SEEDED_CODES)))
    categories = result.scalars().all()
    codes = [c.code for c in categories]

    assert len(codes) == len(set(codes)), "Category codes must be unique"

    await _delete_seeded_categories(db_session)


@pytest.mark.asyncio
async def test_names_are_unique(db_session: AsyncSession) -> None:
    await _delete_seeded_categories(db_session)
    await seed_categories(db_session)

    result = await db_session.execute(select(Category).where(Category.code.in_(SEEDED_CODES)))
    categories = result.scalars().all()
    names = [c.name for c in categories]

    assert len(names) == len(set(names)), "Category names must be unique"

    await _delete_seeded_categories(db_session)


@pytest.mark.asyncio
async def test_total_remains_10_after_repeated_runs(db_session: AsyncSession) -> None:
    await _delete_seeded_categories(db_session)

    for _ in range(3):
        result = await seed_categories(db_session)
        assert result["total"] == 10

    result = await db_session.execute(select(Category).where(Category.code.in_(SEEDED_CODES)))
    assert len(result.scalars().all()) == 10

    await _delete_seeded_categories(db_session)


@pytest.mark.asyncio
async def test_changed_description_is_updated(db_session: AsyncSession) -> None:
    await _delete_seeded_categories(db_session)
    await seed_categories(db_session)

    # Corrupt the HEALTH description
    result = await db_session.execute(select(Category).where(Category.code == "HEALTH"))
    health = result.scalar_one()
    health.description = "Old description"
    await db_session.commit()

    update_result = await seed_categories(db_session)
    assert update_result["updated"] == 1

    result = await db_session.execute(select(Category).where(Category.code == "HEALTH"))
    health_after = result.scalar_one()
    assert (
        "mortality" in health_after.description.lower()
        or "health" in health_after.description.lower()
    ), "Description should be restored to canonical value"

    await _delete_seeded_categories(db_session)


@pytest.mark.asyncio
async def test_changed_name_is_updated(db_session: AsyncSession) -> None:
    await _delete_seeded_categories(db_session)
    await seed_categories(db_session)

    # Corrupt the ECONOMY name
    result = await db_session.execute(select(Category).where(Category.code == "ECONOMY"))
    economy = result.scalar_one()
    economy.name = "Old Economy Name"
    await db_session.commit()

    update_result = await seed_categories(db_session)
    assert update_result["updated"] >= 1

    result = await db_session.execute(select(Category).where(Category.code == "ECONOMY"))
    economy_after = result.scalar_one()
    assert economy_after.name == "Economy"

    await _delete_seeded_categories(db_session)
