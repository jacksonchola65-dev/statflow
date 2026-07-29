"""
Indicator seeder — idempotent.

Seeds core StatFlow indicators grouped by category.
Locates each category by its stable code. If a required category is
missing, a clear error is raised and no indicators are inserted.
If an indicator code already exists, changed fields are updated.
"""
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.category import Category
from app.models.indicator import Indicator


class CategoryNotFoundError(RuntimeError):
    """Raised when a required category is not found in the database."""


@dataclass
class IndicatorRecord:
    code: str
    name: str
    description: str
    unit: str
    source_name: str
    category_code: str  # references Category.code


STATFLOW_INDICATORS: list[IndicatorRecord] = [
    # ── Demographics ───────────────────────────────────────
    IndicatorRecord(
        code="POP_TOTAL",
        name="Total Population",
        description="Total resident population count.",
        unit="People",
        source_name="Zambia Statistics Agency",
        category_code="DEMOGRAPHICS",
    ),
    IndicatorRecord(
        code="POP_GROWTH",
        name="Population Growth Rate",
        description="Annual percentage change in total population.",
        unit="% per year",
        source_name="Zambia Statistics Agency",
        category_code="DEMOGRAPHICS",
    ),
    # ── Education ──────────────────────────────────────────
    IndicatorRecord(
        code="LITERACY_RATE",
        name="Literacy Rate",
        description="Percentage of population aged 15+ who can read and write.",
        unit="%",
        source_name="Zambia Statistics Agency",
        category_code="EDUCATION",
    ),
    IndicatorRecord(
        code="PRIMARY_ENROLMENT",
        name="Primary School Enrolment",
        description="Gross enrolment ratio for primary education.",
        unit="%",
        source_name="Ministry of Education",
        category_code="EDUCATION",
    ),
    # ── Health ─────────────────────────────────────────────
    IndicatorRecord(
        code="LIFE_EXPECTANCY",
        name="Life Expectancy at Birth",
        description="Average number of years a newborn is expected to live.",
        unit="Years",
        source_name="World Health Organization",
        category_code="HEALTH",
    ),
    IndicatorRecord(
        code="UNDER5_MORTALITY",
        name="Under-5 Mortality Rate",
        description="Probability of dying between birth and age 5, per 1,000 live births.",
        unit="Per 1,000 live births",
        source_name="UNICEF",
        category_code="HEALTH",
    ),
    # ── Economy ────────────────────────────────────────────
    IndicatorRecord(
        code="GDP_PER_CAPITA",
        name="GDP per Capita",
        description="Gross domestic product divided by total population.",
        unit="USD",
        source_name="World Bank",
        category_code="ECONOMY",
    ),
    IndicatorRecord(
        code="INFLATION_RATE",
        name="Inflation Rate",
        description="Annual percentage change in the consumer price index.",
        unit="% per year",
        source_name="Bank of Zambia",
        category_code="ECONOMY",
    ),
    # ── Agriculture ────────────────────────────────────────
    IndicatorRecord(
        code="MAIZE_PRODUCTION",
        name="Maize Production",
        description="Total maize harvested in metric tonnes.",
        unit="Metric tonnes",
        source_name="Ministry of Agriculture",
        category_code="AGRICULTURE",
    ),
    IndicatorRecord(
        code="CASSAVA_PRODUCTION",
        name="Cassava Production",
        description="Total cassava harvested in metric tonnes.",
        unit="Metric tonnes",
        source_name="Ministry of Agriculture",
        category_code="AGRICULTURE",
    ),
    # ── Poverty ────────────────────────────────────────────
    IndicatorRecord(
        code="POVERTY_RATE",
        name="Poverty Rate",
        description="Percentage of the population living below the national poverty line.",
        unit="Percent",
        source_name="Zambia Statistics Agency",
        category_code="POVERTY",
    ),
]

# All unique category codes referenced by the indicators above
REQUIRED_CATEGORY_CODES: list[str] = sorted(
    {r.category_code for r in STATFLOW_INDICATORS}
)


async def seed_indicators(session: AsyncSession) -> dict[str, int]:
    """
    Upsert all StatFlow indicators.

    Raises:
        CategoryNotFoundError: if any required category is missing.

    Returns:
        dict with keys 'created', 'updated', 'total'
    """
    # Build category_code → Category.id map; fail clearly on missing categories
    category_map: dict[str, Category] = {}
    missing: list[str] = []

    for code in REQUIRED_CATEGORY_CODES:
        result = await session.execute(
            select(Category).where(Category.code == code)
        )
        category = result.scalar_one_or_none()
        if category is None:
            missing.append(code)
        else:
            category_map[code] = category

    if missing:
        raise CategoryNotFoundError(
            f"Required categories not found: {missing}. "
            "Run the category seeder before the indicator seeder."
        )

    created = 0
    updated = 0

    for record in STATFLOW_INDICATORS:
        category = category_map[record.category_code]

        result = await session.execute(
            select(Indicator).where(Indicator.code == record.code)
        )
        existing = result.scalar_one_or_none()

        if existing is None:
            session.add(
                Indicator(
                    category_id=category.id,
                    code=record.code,
                    name=record.name,
                    description=record.description,
                    unit=record.unit,
                    source_name=record.source_name,
                )
            )
            created += 1
        else:
            changed = False
            for field in ("name", "description", "unit", "source_name"):
                if getattr(existing, field) != getattr(record, field):
                    setattr(existing, field, getattr(record, field))
                    changed = True
            if existing.category_id != category.id:
                existing.category_id = category.id
                changed = True
            if changed:
                updated += 1

    await session.commit()

    return {
        "created": created,
        "updated": updated,
        "total": len(STATFLOW_INDICATORS),
    }
