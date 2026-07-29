"""
District seeder — idempotent.

Currently seeds all 12 districts of Luapula Province (code: LP).
If a district code already exists, its name is updated to match the
canonical value. If Luapula Province is missing, a clear error is raised
and no data is inserted.
"""
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.district import District
from app.models.province import Province


class ProvinceNotFoundError(RuntimeError):
    """Raised when a required province is not found in the database."""


@dataclass
class DistrictRecord:
    code: str
    name: str


LUAPULA_DISTRICTS: list[DistrictRecord] = [
    DistrictRecord("LP-CHEMBE",       "Chembe"),
    DistrictRecord("LP-CHIENGE",      "Chienge"),
    DistrictRecord("LP-CHIFUNABULI",  "Chifunabuli"),
    DistrictRecord("LP-CHIPILI",      "Chipili"),
    DistrictRecord("LP-KAWAMBWA",     "Kawambwa"),
    DistrictRecord("LP-LUNGA",        "Lunga"),
    DistrictRecord("LP-MANSA",        "Mansa"),
    DistrictRecord("LP-MILENGE",      "Milenge"),
    DistrictRecord("LP-MWANSABOMBWE", "Mwansabombwe"),
    DistrictRecord("LP-MWENSE",       "Mwense"),
    DistrictRecord("LP-NCHELENGE",    "Nchelenge"),
    DistrictRecord("LP-SAMFYA",       "Samfya"),
]


async def seed_luapula_districts(session: AsyncSession) -> dict[str, int]:
    """
    Upsert all districts for Luapula Province.

    Raises:
        ProvinceNotFoundError: if Luapula (code=LP) is not in the database.

    Returns:
        dict with keys 'created', 'updated', 'total'
    """
    # Locate the Luapula province — fail clearly if missing
    result = await session.execute(
        select(Province).where(Province.code == "LP")
    )
    luapula = result.scalar_one_or_none()

    if luapula is None:
        raise ProvinceNotFoundError(
            "Luapula Province (code='LP') not found. "
            "Run the province seeder before the district seeder."
        )

    created = 0
    updated = 0

    for record in LUAPULA_DISTRICTS:
        result = await session.execute(
            select(District).where(District.code == record.code)
        )
        existing = result.scalar_one_or_none()

        if existing is None:
            session.add(
                District(
                    province_id=luapula.id,
                    code=record.code,
                    name=record.name,
                )
            )
            created += 1
        elif existing.name != record.name:
            existing.name = record.name
            updated += 1

    await session.commit()

    return {
        "created": created,
        "updated": updated,
        "total": len(LUAPULA_DISTRICTS),
    }
