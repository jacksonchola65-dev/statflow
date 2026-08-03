"""
Province seeder — idempotent.
Inserts all 10 Zambian provinces. If a province code already exists,
its name is updated to match the canonical value.
"""

from dataclasses import dataclass

from app.models.province import Province
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


@dataclass
class ProvinceRecord:
    code: str
    name: str


ZAMBIA_PROVINCES: list[ProvinceRecord] = [
    ProvinceRecord("CP", "Central"),
    ProvinceRecord("CB", "Copperbelt"),
    ProvinceRecord("EA", "Eastern"),
    ProvinceRecord("LP", "Luapula"),
    ProvinceRecord("LK", "Lusaka"),
    ProvinceRecord("MU", "Muchinga"),
    ProvinceRecord("NW", "North-Western"),
    ProvinceRecord("NR", "Northern"),
    ProvinceRecord("SO", "Southern"),
    ProvinceRecord("WE", "Western"),
]


async def seed_provinces(session: AsyncSession) -> dict[str, int]:
    """
    Upsert all Zambian provinces.

    Returns:
        dict with keys 'created', 'updated', 'total'
    """
    created = 0
    updated = 0

    for record in ZAMBIA_PROVINCES:
        result = await session.execute(select(Province).where(Province.code == record.code))
        existing = result.scalar_one_or_none()

        if existing is None:
            session.add(Province(code=record.code, name=record.name))
            created += 1
        elif existing.name != record.name:
            existing.name = record.name
            updated += 1

    await session.commit()

    return {
        "created": created,
        "updated": updated,
        "total": created + updated + (len(ZAMBIA_PROVINCES) - created - updated),
    }
