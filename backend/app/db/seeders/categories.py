"""
Category seeder — idempotent.

Seeds all core StatFlow indicator categories.
If a category code already exists, its name and description are updated
to match the canonical values. Missing categories are inserted.
"""

from dataclasses import dataclass

from app.models.category import Category
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


@dataclass
class CategoryRecord:
    code: str
    name: str
    description: str


STATFLOW_CATEGORIES: list[CategoryRecord] = [
    CategoryRecord(
        "DEMOGRAPHICS",
        "Demographics",
        "Population size, structure, distribution, and demographic change.",
    ),
    CategoryRecord(
        "EDUCATION",
        "Education",
        "Literacy, enrolment, attainment, and school infrastructure indicators.",
    ),
    CategoryRecord(
        "HEALTH",
        "Health",
        "Mortality, morbidity, nutrition, and access to health services.",
    ),
    CategoryRecord(
        "ECONOMY",
        "Economy",
        "GDP, trade, fiscal performance, and macroeconomic stability indicators.",
    ),
    CategoryRecord(
        "AGRICULTURE",
        "Agriculture",
        "Crop production, land use, food security, and agricultural inputs.",
    ),
    CategoryRecord(
        "EMPLOYMENT",
        "Employment",
        "Labour force participation, unemployment, wages, and working conditions.",
    ),
    CategoryRecord(
        "POVERTY",
        "Poverty",
        "Poverty headcount, inequality, and household welfare measures.",
    ),
    CategoryRecord(
        "INFRASTRUCTURE",
        "Infrastructure",
        "Roads, energy access, telecommunications, and public facilities.",
    ),
    CategoryRecord(
        "WATER_SANITATION",
        "Water and Sanitation",
        "Access to safe drinking water, sanitation facilities, and hygiene.",
    ),
    CategoryRecord(
        "ENVIRONMENT",
        "Environment",
        "Deforestation, emissions, land degradation, and climate indicators.",
    ),
]


async def seed_categories(session: AsyncSession) -> dict[str, int]:
    """
    Upsert all StatFlow indicator categories.

    Returns:
        dict with keys 'created', 'updated', 'total'
    """
    created = 0
    updated = 0

    for record in STATFLOW_CATEGORIES:
        result = await session.execute(select(Category).where(Category.code == record.code))
        existing = result.scalar_one_or_none()

        if existing is None:
            session.add(
                Category(
                    code=record.code,
                    name=record.name,
                    description=record.description,
                )
            )
            created += 1
        else:
            changed = False
            if existing.name != record.name:
                existing.name = record.name
                changed = True
            if existing.description != record.description:
                existing.description = record.description
                changed = True
            if changed:
                updated += 1

    await session.commit()

    return {
        "created": created,
        "updated": updated,
        "total": len(STATFLOW_CATEGORIES),
    }
