"""
Tests for:
  - app.db.seeders.datasets.seed_datasets
  - app.db.seeders.data_points.seed_demo_data_points

Each test manages its own cleanup to keep tests independent.
"""

from decimal import Decimal

import pytest
from app.db.seeders.categories import seed_categories
from app.db.seeders.data_points import (
    DEMO_DATASET_NAME,
    DEMO_REFERENCE_YEAR,
    DataPointSeedError,
    seed_demo_data_points,
)
from app.db.seeders.datasets import DEMO_DATASET, seed_datasets
from app.db.seeders.indicators import seed_indicators
from app.models.data_point import DataPoint
from app.models.dataset import Dataset
from app.models.indicator import Indicator
from app.models.province import Province
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _delete_demo_dataset(session: AsyncSession) -> None:
    """Delete the demo dataset (cascades to data_points via ON DELETE CASCADE)."""
    await session.execute(
        delete(Dataset).where(
            Dataset.name == DEMO_DATASET_NAME,
            Dataset.reference_year == DEMO_REFERENCE_YEAR,
        )
    )
    await session.commit()


async def _ensure_dependencies(session: AsyncSession) -> None:
    """Ensure categories and indicators are present (idempotent)."""
    await seed_categories(session)
    await seed_indicators(session)


async def _get_demo_dataset(session: AsyncSession) -> Dataset | None:
    result = await session.execute(
        select(Dataset).where(
            Dataset.name == DEMO_DATASET_NAME,
            Dataset.reference_year == DEMO_REFERENCE_YEAR,
        )
    )
    return result.scalar_one_or_none()


async def _get_demo_data_points(session: AsyncSession) -> list[DataPoint]:
    ds = await _get_demo_dataset(session)
    if ds is None:
        return []
    result = await session.execute(select(DataPoint).where(DataPoint.dataset_id == ds.id))
    return list(result.scalars().all())


# ---------------------------------------------------------------------------
# Dataset seeder tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_dataset_first_run_creates_record(db_session: AsyncSession) -> None:
    await _delete_demo_dataset(db_session)

    result = await seed_datasets(db_session)

    assert result["created"] == 1
    assert result["updated"] == 0
    assert result["total"] == 1

    ds = await _get_demo_dataset(db_session)
    assert ds is not None
    assert ds.name == DEMO_DATASET.name
    assert ds.reference_year == DEMO_DATASET.reference_year
    assert ds.is_published is True

    await _delete_demo_dataset(db_session)


@pytest.mark.asyncio
async def test_dataset_second_run_is_idempotent(db_session: AsyncSession) -> None:
    await _delete_demo_dataset(db_session)
    await seed_datasets(db_session)

    second = await seed_datasets(db_session)

    assert second["created"] == 0
    assert second["total"] == 1

    # Verify only one record exists
    result = await db_session.execute(
        select(Dataset).where(
            Dataset.name == DEMO_DATASET_NAME,
            Dataset.reference_year == DEMO_REFERENCE_YEAR,
        )
    )
    rows = result.scalars().all()
    assert len(rows) == 1

    await _delete_demo_dataset(db_session)


@pytest.mark.asyncio
async def test_dataset_metadata_update(db_session: AsyncSession) -> None:
    await _delete_demo_dataset(db_session)
    await seed_datasets(db_session)

    # Corrupt the source_name
    ds = await _get_demo_dataset(db_session)
    ds.source_name = "Old Source"
    await db_session.commit()

    update_result = await seed_datasets(db_session)
    assert update_result["updated"] == 1

    ds_after = await _get_demo_dataset(db_session)
    assert ds_after.source_name == DEMO_DATASET.source_name

    await _delete_demo_dataset(db_session)


# ---------------------------------------------------------------------------
# Data-point seeder tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_data_points_first_run_creates_60(db_session: AsyncSession) -> None:
    await _ensure_dependencies(db_session)
    await _delete_demo_dataset(db_session)
    await seed_datasets(db_session)

    result = await seed_demo_data_points(db_session)

    assert result["created"] == 60
    assert result["updated"] == 0
    assert result["total"] == 60

    await _delete_demo_dataset(db_session)


@pytest.mark.asyncio
async def test_data_points_second_run_is_idempotent(db_session: AsyncSession) -> None:
    await _ensure_dependencies(db_session)
    await _delete_demo_dataset(db_session)
    await seed_datasets(db_session)
    await seed_demo_data_points(db_session)

    second = await seed_demo_data_points(db_session)

    assert second["created"] == 0
    assert second["total"] == 60

    points = await _get_demo_data_points(db_session)
    assert len(points) == 60

    await _delete_demo_dataset(db_session)


@pytest.mark.asyncio
async def test_all_data_points_are_province_level(db_session: AsyncSession) -> None:
    await _ensure_dependencies(db_session)
    await _delete_demo_dataset(db_session)
    await seed_datasets(db_session)
    await seed_demo_data_points(db_session)

    points = await _get_demo_data_points(db_session)
    assert all(p.province_id is not None for p in points)
    assert all(p.district_id is None for p in points)

    await _delete_demo_dataset(db_session)


@pytest.mark.asyncio
async def test_all_data_points_use_reference_year_2023(db_session: AsyncSession) -> None:
    await _ensure_dependencies(db_session)
    await _delete_demo_dataset(db_session)
    await seed_datasets(db_session)
    await seed_demo_data_points(db_session)

    points = await _get_demo_data_points(db_session)
    assert all(p.reference_year == 2023 for p in points)

    await _delete_demo_dataset(db_session)


@pytest.mark.asyncio
async def test_data_point_value_update(db_session: AsyncSession) -> None:
    await _ensure_dependencies(db_session)
    await _delete_demo_dataset(db_session)
    await seed_datasets(db_session)
    await seed_demo_data_points(db_session)

    # Corrupt one value — Lusaka (LK) LITERACY_RATE
    ds = await _get_demo_dataset(db_session)
    prov_result = await db_session.execute(select(Province).where(Province.code == "LK"))
    lusaka = prov_result.scalar_one()
    ind_result = await db_session.execute(
        select(Indicator).where(Indicator.code == "LITERACY_RATE")
    )
    lit_rate = ind_result.scalar_one()

    dp_result = await db_session.execute(
        select(DataPoint).where(
            DataPoint.dataset_id == ds.id,
            DataPoint.indicator_id == lit_rate.id,
            DataPoint.province_id == lusaka.id,
        )
    )
    dp = dp_result.scalar_one()
    dp.value = Decimal("0.0001")
    await db_session.commit()

    update_result = await seed_demo_data_points(db_session)
    assert update_result["updated"] >= 1

    dp_result = await db_session.execute(
        select(DataPoint).where(
            DataPoint.dataset_id == ds.id,
            DataPoint.indicator_id == lit_rate.id,
            DataPoint.province_id == lusaka.id,
        )
    )
    dp_after = dp_result.scalar_one()
    assert dp_after.value == Decimal("87.5")

    await _delete_demo_dataset(db_session)


@pytest.mark.asyncio
async def test_missing_dataset_raises_clear_error(db_session: AsyncSession) -> None:
    await _ensure_dependencies(db_session)
    await _delete_demo_dataset(db_session)

    with pytest.raises(DataPointSeedError) as exc_info:
        await seed_demo_data_points(db_session)

    assert DEMO_DATASET_NAME in str(exc_info.value)
    assert "dataset seeder" in str(exc_info.value).lower()


@pytest.mark.asyncio
async def test_missing_indicator_raises_clear_error(db_session: AsyncSession) -> None:
    """If POVERTY_RATE is deleted, the seeder must fail clearly."""
    await _ensure_dependencies(db_session)
    await _delete_demo_dataset(db_session)
    await seed_datasets(db_session)

    # Delete POVERTY_RATE indicator — first delete any data_points referencing it
    ind_result = await db_session.execute(select(Indicator).where(Indicator.code == "POVERTY_RATE"))
    poverty_rate = ind_result.scalar_one_or_none()
    if poverty_rate is None:
        pytest.skip("POVERTY_RATE not present")

    await db_session.execute(delete(DataPoint).where(DataPoint.indicator_id == poverty_rate.id))
    await db_session.execute(delete(Indicator).where(Indicator.code == "POVERTY_RATE"))
    await db_session.commit()

    with pytest.raises(DataPointSeedError) as exc_info:
        await seed_demo_data_points(db_session)

    assert "POVERTY_RATE" in str(exc_info.value)

    # Restore indicator
    await seed_indicators(db_session)
    await _delete_demo_dataset(db_session)
