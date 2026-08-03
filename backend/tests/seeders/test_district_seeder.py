"""
Tests for app.db.seeders.districts.seed_luapula_districts

The test database already has all 10 provinces seeded by setup_test_database.
Each test that inserts districts cleans up afterwards to keep tests
independent (since the shared database is not reset between individual tests).
"""

import pytest
from app.db.seeders.districts import (
    ProvinceNotFoundError,
    seed_luapula_districts,
)
from app.models.district import District
from app.models.province import Province
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


async def _delete_luapula_districts(session: AsyncSession) -> None:
    """Remove all LP-prefixed districts — used for test cleanup."""
    await session.execute(delete(District).where(District.code.like("LP-%")))
    await session.commit()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_first_run_creates_12_districts(db_session: AsyncSession) -> None:
    await _delete_luapula_districts(db_session)

    result = await seed_luapula_districts(db_session)

    assert result["created"] == 12
    assert result["updated"] == 0
    assert result["total"] == 12

    await _delete_luapula_districts(db_session)


@pytest.mark.asyncio
async def test_second_run_creates_no_duplicates(db_session: AsyncSession) -> None:
    await _delete_luapula_districts(db_session)

    await seed_luapula_districts(db_session)
    second = await seed_luapula_districts(db_session)

    assert second["created"] == 0
    assert second["total"] == 12

    # Verify actual row count in the database
    count_result = await db_session.execute(select(District).where(District.code.like("LP-%")))
    rows = count_result.scalars().all()
    assert len(rows) == 12

    await _delete_luapula_districts(db_session)


@pytest.mark.asyncio
async def test_all_districts_belong_to_luapula(db_session: AsyncSession) -> None:
    await _delete_luapula_districts(db_session)
    await seed_luapula_districts(db_session)

    # Get Luapula province id
    prov_result = await db_session.execute(select(Province).where(Province.code == "LP"))
    luapula = prov_result.scalar_one()

    dist_result = await db_session.execute(select(District).where(District.code.like("LP-%")))
    districts = dist_result.scalars().all()

    assert all(d.province_id == luapula.id for d in districts), (
        "All Luapula districts must have province_id == Luapula.id"
    )

    await _delete_luapula_districts(db_session)


@pytest.mark.asyncio
async def test_all_codes_are_unique(db_session: AsyncSession) -> None:
    await _delete_luapula_districts(db_session)
    await seed_luapula_districts(db_session)

    result = await db_session.execute(select(District).where(District.code.like("LP-%")))
    districts = result.scalars().all()
    codes = [d.code for d in districts]

    assert len(codes) == len(set(codes)), "District codes must be unique"

    await _delete_luapula_districts(db_session)


@pytest.mark.asyncio
async def test_missing_luapula_raises_clear_error(db_session: AsyncSession) -> None:
    """If Luapula province is deleted, the seeder must raise ProvinceNotFoundError."""
    from app.models.data_point import DataPoint as DP

    # First clean up any LP districts (which may have data_points referencing them)
    await _delete_luapula_districts(db_session)

    # Clean up any data_points referencing Luapula province before deleting it
    result = await db_session.execute(select(Province).where(Province.code == "LP"))
    luapula = result.scalar_one_or_none()
    if luapula is None:
        pytest.skip("Luapula not present — skipping")

    await db_session.execute(delete(DP).where(DP.province_id == luapula.id))
    await db_session.commit()

    # Now delete Luapula
    await db_session.execute(delete(Province).where(Province.code == "LP"))
    await db_session.commit()

    with pytest.raises(ProvinceNotFoundError) as exc_info:
        await seed_luapula_districts(db_session)

    assert "LP" in str(exc_info.value)
    assert "province seeder" in str(exc_info.value).lower()

    # Restore Luapula so other tests are not affected
    db_session.add(Province(code="LP", name="Luapula"))
    await db_session.commit()


@pytest.mark.asyncio
async def test_update_changes_district_name(db_session: AsyncSession) -> None:
    """If a district name differs from canonical, it is updated."""
    await _delete_luapula_districts(db_session)
    await seed_luapula_districts(db_session)

    # Corrupt one district name directly
    result = await db_session.execute(select(District).where(District.code == "LP-MANSA"))
    mansa = result.scalar_one()
    mansa.name = "Old Mansa Name"
    await db_session.commit()

    # Re-run seeder — it should update the name back
    update_result = await seed_luapula_districts(db_session)
    assert update_result["updated"] == 1

    result = await db_session.execute(select(District).where(District.code == "LP-MANSA"))
    mansa_after = result.scalar_one()
    assert mansa_after.name == "Mansa"

    await _delete_luapula_districts(db_session)
