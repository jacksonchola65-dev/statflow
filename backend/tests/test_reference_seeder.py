import pytest
from app.db.seeders.reference import (
    ReferenceDataConflictError,
    bootstrap_reference_data,
)
from app.models.category import Category
from app.models.data_point import DataPoint
from app.models.dataset import Dataset
from app.models.district import District
from app.models.indicator import Indicator
from app.models.province import Province
from app.models.user import User
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


@pytest.mark.asyncio
async def test_reference_bootstrap_creates_only_canonical_reference_data(
    db_session: AsyncSession,
) -> None:
    await bootstrap_reference_data(db_session)

    categories = (await db_session.execute(select(Category))).scalars().all()
    provinces = (await db_session.execute(select(Province))).scalars().all()
    districts = (
        (
            await db_session.execute(
                select(District).where(
                    District.province_id == next(p.id for p in provinces if p.code == "LP")
                )
            )
        )
        .scalars()
        .all()
    )
    indicators = (await db_session.execute(select(Indicator))).scalars().all()
    datasets = (await db_session.execute(select(Dataset))).scalars().all()
    data_points = (await db_session.execute(select(DataPoint))).scalars().all()
    users = (await db_session.execute(select(User))).scalars().all()

    assert len(categories) == 10
    assert len(provinces) == 10
    assert {district.code for district in districts} == {
        "LP-CHEMBE",
        "LP-CHIENGE",
        "LP-CHIFUNABULI",
        "LP-CHIPILI",
        "LP-KAWAMBWA",
        "LP-LUNGA",
        "LP-MANSA",
        "LP-MILENGE",
        "LP-MWANSABOMBWE",
        "LP-MWENSE",
        "LP-NCHELENGE",
        "LP-SAMFYA",
    }
    assert len(districts) == 12
    assert len(indicators) == 11
    assert len(datasets) == 0
    assert len(data_points) == 0
    assert len(users) == 0

    pop_total = next(indicator for indicator in indicators if indicator.code == "POP_TOTAL")
    demographics = next(category for category in categories if category.code == "DEMOGRAPHICS")
    assert pop_total.name == "Total Population"
    assert pop_total.unit == "People"
    assert pop_total.category_id == demographics.id


@pytest.mark.asyncio
async def test_reference_bootstrap_is_idempotent(db_session: AsyncSession) -> None:
    await bootstrap_reference_data(db_session)
    first_ids = {
        "categories": {
            row.code: row.id for row in (await db_session.execute(select(Category))).scalars()
        },
        "provinces": {
            row.code: row.id for row in (await db_session.execute(select(Province))).scalars()
        },
        "districts": {
            row.code: row.id for row in (await db_session.execute(select(District))).scalars()
        },
        "indicators": {
            row.code: row.id for row in (await db_session.execute(select(Indicator))).scalars()
        },
    }

    await bootstrap_reference_data(db_session)
    second_ids = {
        "categories": {
            row.code: row.id for row in (await db_session.execute(select(Category))).scalars()
        },
        "provinces": {
            row.code: row.id for row in (await db_session.execute(select(Province))).scalars()
        },
        "districts": {
            row.code: row.id for row in (await db_session.execute(select(District))).scalars()
        },
        "indicators": {
            row.code: row.id for row in (await db_session.execute(select(Indicator))).scalars()
        },
    }
    assert second_ids == first_ids


@pytest.mark.asyncio
async def test_reference_bootstrap_rejects_canonical_conflict_without_writes(
    db_session: AsyncSession,
) -> None:
    await bootstrap_reference_data(db_session)
    province = (
        await db_session.execute(select(Province).where(Province.code == "LP"))
    ).scalar_one()
    province.name = "Conflicting Province"
    await db_session.commit()

    with pytest.raises(ReferenceDataConflictError, match="province LP"):
        await bootstrap_reference_data(db_session)
