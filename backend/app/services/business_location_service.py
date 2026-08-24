from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from app.domain.decision.contracts import (
    DecisionAlternative,
    EligibilityState,
)
from app.models.district import District
from app.models.province import Province
from app.repositories.district_repository import DistrictRepository
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


@dataclass(frozen=True)
class BusinessLocationCandidateResolution:
    province: Province
    candidates: tuple[DecisionAlternative, ...]
    excluded: tuple[DecisionAlternative, ...]


def resolve_district_candidates(
    province: Province,
    districts: Iterable[District],
) -> BusinessLocationCandidateResolution:
    candidates: list[DecisionAlternative] = []
    excluded: list[DecisionAlternative] = []
    for district in sorted(districts, key=lambda item: (item.name.casefold(), item.code)):
        alternative = DecisionAlternative(
            identifier=str(district.id),
            display_name=district.name,
            alternative_type="district",
            metadata={"code": district.code, "province_code": province.code},
        )
        if district.province_id == province.id:
            candidates.append(alternative)
        else:
            excluded.append(
                alternative.model_copy(
                    update={
                        "eligibility": EligibilityState.EXCLUDED,
                        "exclusion_reasons": ("district is outside the requested province",),
                    }
                )
            )
    return BusinessLocationCandidateResolution(
        province=province,
        candidates=tuple(candidates),
        excluded=tuple(excluded),
    )


async def resolve_district_candidates_by_province(
    session: AsyncSession,
    province_code: str,
) -> BusinessLocationCandidateResolution:
    province_result = await session.execute(select(Province).where(Province.code == province_code))
    province = province_result.scalar_one_or_none()
    if province is None:
        raise ValueError(f"province code not found: {province_code}")
    districts = await DistrictRepository(session).get_all_districts()
    return resolve_district_candidates(province, districts)
