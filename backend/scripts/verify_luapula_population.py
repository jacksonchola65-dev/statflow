"""Read-only verification of the controlled Luapula population evidence."""

import asyncio
import sys
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.core.config import normalize_async_database_url, settings  # noqa: E402
from app.models.data_point import DataPoint  # noqa: E402
from app.models.dataset import Dataset  # noqa: E402
from app.models.district import District  # noqa: E402
from app.models.indicator import Indicator  # noqa: E402
from app.models.province import Province  # noqa: E402

EXPECTED_CODES = {
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


async def verify() -> None:
    engine = create_async_engine(
        normalize_async_database_url(settings.DATABASE_URL), pool_pre_ping=True
    )
    factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with factory() as session:
        province = (
            await session.execute(select(Province).where(Province.code == "LP"))
        ).scalar_one()
        indicator = (
            await session.execute(select(Indicator).where(Indicator.code == "POP_TOTAL"))
        ).scalar_one()
        rows = (
            await session.execute(
                select(DataPoint, District, Dataset)
                .join(District, DataPoint.district_id == District.id)
                .join(Dataset, DataPoint.dataset_id == Dataset.id)
                .where(District.province_id == province.id, DataPoint.indicator_id == indicator.id)
                .where(DataPoint.reference_year == 2022)
            )
        ).all()
        codes = {district.code for _, district, _ in rows}
        duplicates = (
            await session.execute(
                select(DataPoint.district_id, func.count(DataPoint.id))
                .where(DataPoint.indicator_id == indicator.id, DataPoint.reference_year == 2022)
                .group_by(DataPoint.district_id)
                .having(func.count(DataPoint.id) > 1)
            )
        ).all()
        mansa = next((point for point, district, _ in rows if district.code == "LP-MANSA"), None)
        if (
            len(rows) != 12
            or codes != EXPECTED_CODES
            or duplicates
            or mansa is None
            or float(mansa.value) != 329622.0
            or any(
                dataset.source_name != "Zambia Statistics Agency (ZamStats)"
                or not dataset.source_url
                or "zamstats.gov.zm" not in dataset.source_url
                for _, _, dataset in rows
            )
        ):
            raise RuntimeError("Luapula 2022 POP_TOTAL verification failed")
        print("Luapula evidence verified: 12/12, ZamStats, 2022, no duplicates, Mansa=329622")
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(verify())
