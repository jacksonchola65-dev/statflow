"""
Data-point seeder — idempotent.

Seeds province-level 2023 demonstration data for selected indicators across
all 10 Zambian provinces. Values are illustrative and are not official statistics.

Natural key: dataset_id + indicator_id + province_id + reference_year
(enforced by the partial unique index uix_data_points_province_level).
"""
from dataclasses import dataclass
from decimal import Decimal
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.data_point import DataPoint
from app.models.dataset import Dataset
from app.models.indicator import Indicator
from app.models.province import Province


class DataPointSeedError(RuntimeError):
    """Raised when a required dependency is missing during seeding."""


@dataclass
class DataPointRecord:
    province_code: str
    indicator_code: str
    value: Decimal


# ---------------------------------------------------------------------------
# Demonstration values — illustrative only, not official statistics
# ---------------------------------------------------------------------------

DEMO_DATA: list[DataPointRecord] = [
    # ── POP_TOTAL (thousands of people) ────────────────────
    DataPointRecord("CP", "POP_TOTAL", Decimal("2167000")),
    DataPointRecord("CB", "POP_TOTAL", Decimal("2556000")),
    DataPointRecord("EA", "POP_TOTAL", Decimal("1973000")),
    DataPointRecord("LP", "POP_TOTAL", Decimal("1051000")),
    DataPointRecord("LK", "POP_TOTAL", Decimal("3360000")),
    DataPointRecord("MU", "POP_TOTAL", Decimal("804000")),
    DataPointRecord("NW", "POP_TOTAL", Decimal("836000")),
    DataPointRecord("NR", "POP_TOTAL", Decimal("1527000")),
    DataPointRecord("SO", "POP_TOTAL", Decimal("1915000")),
    DataPointRecord("WE", "POP_TOTAL", Decimal("991000")),

    # ── LITERACY_RATE (%) ──────────────────────────────────
    DataPointRecord("CP", "LITERACY_RATE", Decimal("72.4")),
    DataPointRecord("CB", "LITERACY_RATE", Decimal("83.1")),
    DataPointRecord("EA", "LITERACY_RATE", Decimal("64.8")),
    DataPointRecord("LP", "LITERACY_RATE", Decimal("61.2")),
    DataPointRecord("LK", "LITERACY_RATE", Decimal("87.5")),
    DataPointRecord("MU", "LITERACY_RATE", Decimal("58.9")),
    DataPointRecord("NW", "LITERACY_RATE", Decimal("66.3")),
    DataPointRecord("NR", "LITERACY_RATE", Decimal("63.7")),
    DataPointRecord("SO", "LITERACY_RATE", Decimal("69.0")),
    DataPointRecord("WE", "LITERACY_RATE", Decimal("55.4")),

    # ── LIFE_EXPECTANCY (years) ────────────────────────────
    DataPointRecord("CP", "LIFE_EXPECTANCY", Decimal("57.8")),
    DataPointRecord("CB", "LIFE_EXPECTANCY", Decimal("59.2")),
    DataPointRecord("EA", "LIFE_EXPECTANCY", Decimal("55.6")),
    DataPointRecord("LP", "LIFE_EXPECTANCY", Decimal("54.1")),
    DataPointRecord("LK", "LIFE_EXPECTANCY", Decimal("61.3")),
    DataPointRecord("MU", "LIFE_EXPECTANCY", Decimal("53.7")),
    DataPointRecord("NW", "LIFE_EXPECTANCY", Decimal("56.4")),
    DataPointRecord("NR", "LIFE_EXPECTANCY", Decimal("55.0")),
    DataPointRecord("SO", "LIFE_EXPECTANCY", Decimal("57.2")),
    DataPointRecord("WE", "LIFE_EXPECTANCY", Decimal("52.9")),

    # ── GDP_PER_CAPITA (USD) ───────────────────────────────
    DataPointRecord("CP", "GDP_PER_CAPITA", Decimal("1420")),
    DataPointRecord("CB", "GDP_PER_CAPITA", Decimal("2180")),
    DataPointRecord("EA", "GDP_PER_CAPITA", Decimal("980")),
    DataPointRecord("LP", "GDP_PER_CAPITA", Decimal("870")),
    DataPointRecord("LK", "GDP_PER_CAPITA", Decimal("3100")),
    DataPointRecord("MU", "GDP_PER_CAPITA", Decimal("750")),
    DataPointRecord("NW", "GDP_PER_CAPITA", Decimal("1640")),
    DataPointRecord("NR", "GDP_PER_CAPITA", Decimal("890")),
    DataPointRecord("SO", "GDP_PER_CAPITA", Decimal("1150")),
    DataPointRecord("WE", "GDP_PER_CAPITA", Decimal("680")),

    # ── MAIZE_PRODUCTION (metric tonnes) ──────────────────
    DataPointRecord("CP", "MAIZE_PRODUCTION", Decimal("485000")),
    DataPointRecord("CB", "MAIZE_PRODUCTION", Decimal("312000")),
    DataPointRecord("EA", "MAIZE_PRODUCTION", Decimal("695000")),
    DataPointRecord("LP", "MAIZE_PRODUCTION", Decimal("198000")),
    DataPointRecord("LK", "MAIZE_PRODUCTION", Decimal("124000")),
    DataPointRecord("MU", "MAIZE_PRODUCTION", Decimal("267000")),
    DataPointRecord("NW", "MAIZE_PRODUCTION", Decimal("341000")),
    DataPointRecord("NR", "MAIZE_PRODUCTION", Decimal("423000")),
    DataPointRecord("SO", "MAIZE_PRODUCTION", Decimal("578000")),
    DataPointRecord("WE", "MAIZE_PRODUCTION", Decimal("89000")),

    # ── POVERTY_RATE (%) ───────────────────────────────────
    DataPointRecord("CP", "POVERTY_RATE", Decimal("55.2")),
    DataPointRecord("CB", "POVERTY_RATE", Decimal("39.8")),
    DataPointRecord("EA", "POVERTY_RATE", Decimal("70.1")),
    DataPointRecord("LP", "POVERTY_RATE", Decimal("72.4")),
    DataPointRecord("LK", "POVERTY_RATE", Decimal("24.3")),
    DataPointRecord("MU", "POVERTY_RATE", Decimal("76.8")),
    DataPointRecord("NW", "POVERTY_RATE", Decimal("63.5")),
    DataPointRecord("NR", "POVERTY_RATE", Decimal("68.9")),
    DataPointRecord("SO", "POVERTY_RATE", Decimal("57.6")),
    DataPointRecord("WE", "POVERTY_RATE", Decimal("75.3")),
]

DEMO_DATASET_NAME = "Zambia Provincial Development Indicators"
DEMO_REFERENCE_YEAR = 2023
EXPECTED_TOTAL = len(DEMO_DATA)  # 60 records (6 indicators × 10 provinces)


async def seed_demo_data_points(session: AsyncSession) -> dict[str, int]:
    """
    Upsert all demonstration data points.

    Raises:
        DataPointSeedError: if the dataset, any indicator, or any province is missing.

    Returns:
        dict with keys 'created', 'updated', 'total'
    """
    # ── Locate dataset ─────────────────────────────────────
    ds_result = await session.execute(
        select(Dataset).where(
            Dataset.name == DEMO_DATASET_NAME,
            Dataset.reference_year == DEMO_REFERENCE_YEAR,
        )
    )
    dataset = ds_result.scalar_one_or_none()
    if dataset is None:
        raise DataPointSeedError(
            f"Dataset '{DEMO_DATASET_NAME}' (year={DEMO_REFERENCE_YEAR}) not found. "
            "Run the dataset seeder first."
        )

    # ── Build indicator code → Indicator map ──────────────
    indicator_codes = sorted({r.indicator_code for r in DEMO_DATA})
    indicator_map: dict[str, Indicator] = {}
    missing_indicators: list[str] = []
    for code in indicator_codes:
        ind_result = await session.execute(
            select(Indicator).where(Indicator.code == code)
        )
        ind = ind_result.scalar_one_or_none()
        if ind is None:
            missing_indicators.append(code)
        else:
            indicator_map[code] = ind

    if missing_indicators:
        raise DataPointSeedError(
            f"Indicators not found: {missing_indicators}. "
            "Run the indicator seeder first."
        )

    # ── Build province code → Province map ────────────────
    province_codes = sorted({r.province_code for r in DEMO_DATA})
    province_map: dict[str, Province] = {}
    missing_provinces: list[str] = []
    for code in province_codes:
        prov_result = await session.execute(
            select(Province).where(Province.code == code)
        )
        prov = prov_result.scalar_one_or_none()
        if prov is None:
            missing_provinces.append(code)
        else:
            province_map[code] = prov

    if missing_provinces:
        raise DataPointSeedError(
            f"Provinces not found: {missing_provinces}. "
            "Run the province seeder first."
        )

    # ── Upsert data points ────────────────────────────────
    created = 0
    updated = 0

    for record in DEMO_DATA:
        indicator = indicator_map[record.indicator_code]
        province = province_map[record.province_code]

        existing_result = await session.execute(
            select(DataPoint).where(
                DataPoint.dataset_id == dataset.id,
                DataPoint.indicator_id == indicator.id,
                DataPoint.province_id == province.id,
                DataPoint.district_id.is_(None),
                DataPoint.reference_year == DEMO_REFERENCE_YEAR,
            )
        )
        existing = existing_result.scalar_one_or_none()

        if existing is None:
            session.add(
                DataPoint(
                    dataset_id=dataset.id,
                    indicator_id=indicator.id,
                    province_id=province.id,
                    district_id=None,
                    reference_year=DEMO_REFERENCE_YEAR,
                    value=record.value,
                )
            )
            created += 1
        else:
            if existing.value != record.value:
                existing.value = record.value
                updated += 1

    await session.commit()

    return {"created": created, "updated": updated, "total": EXPECTED_TOTAL}
