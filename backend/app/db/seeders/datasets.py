"""
Dataset seeder — idempotent.

Seeds the StatFlow demonstration dataset.
Located by name + reference_year; created if missing, updated if metadata changed.
"""
from dataclasses import dataclass
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.dataset import Dataset


@dataclass
class DatasetRecord:
    name: str
    description: str
    source_name: str
    source_url: Optional[str]
    reference_year: int
    is_published: bool


DEMO_DATASET = DatasetRecord(
    name="Zambia Provincial Development Indicators",
    description=(
        "Demonstration dataset containing selected provincial development "
        "indicators for the StatFlow MVP. Values are illustrative and should "
        "not be cited as official statistics."
    ),
    source_name="StatFlow Demonstration Data",
    source_url=None,
    reference_year=2023,
    is_published=True,
)

# Natural key used to locate the record
_LOOKUP_NAME = DEMO_DATASET.name
_LOOKUP_YEAR = DEMO_DATASET.reference_year


async def seed_datasets(session: AsyncSession) -> dict[str, int]:
    """
    Upsert the StatFlow demonstration dataset.

    Returns:
        dict with keys 'created', 'updated', 'total'
    """
    result = await session.execute(
        select(Dataset).where(
            Dataset.name == _LOOKUP_NAME,
            Dataset.reference_year == _LOOKUP_YEAR,
        )
    )
    existing = result.scalar_one_or_none()

    created = 0
    updated = 0

    if existing is None:
        session.add(
            Dataset(
                name=DEMO_DATASET.name,
                description=DEMO_DATASET.description,
                source_name=DEMO_DATASET.source_name,
                source_url=DEMO_DATASET.source_url,
                reference_year=DEMO_DATASET.reference_year,
                is_published=DEMO_DATASET.is_published,
            )
        )
        created = 1
    else:
        changed = False
        for field in ("description", "source_name", "source_url", "is_published"):
            canonical = getattr(DEMO_DATASET, field)
            if getattr(existing, field) != canonical:
                setattr(existing, field, canonical)
                changed = True
        if changed:
            updated = 1

    await session.commit()

    return {"created": created, "updated": updated, "total": 1}
