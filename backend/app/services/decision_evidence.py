from __future__ import annotations

from datetime import date
from uuid import UUID

from app.domain.decision.contracts import (
    DecisionAlternative,
    DecisionRequest,
    Evidence,
    EvidenceQuality,
    FreshnessStatus,
    GeographicLevel,
    IndicatorRequirement,
)
from app.domain.decision.resolver import EvidenceResolution, EvidenceResolutionStatus
from app.models.data_point import DataPoint
from app.models.dataset import Dataset
from app.models.district import District
from app.models.indicator import Indicator
from app.models.province import Province
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


class DecisionEvidenceResolver:
    """SQLAlchemy adapter translating legacy statistical observations to Evidence."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def resolve(
        self,
        requirement: IndicatorRequirement,
        alternative: DecisionAlternative,
        request: DecisionRequest,
        *,
        as_of: date | None = None,
    ) -> EvidenceResolution:
        expected_level = requirement.geographic_level
        actual_level = self._alternative_level(alternative)
        if (
            expected_level is not None
            and actual_level is not None
            and expected_level is not actual_level
        ):
            return EvidenceResolution(
                status=EvidenceResolutionStatus.GEOGRAPHICALLY_INCOMPATIBLE,
                detail="alternative geography level does not satisfy the indicator requirement",
            )

        try:
            indicator_id = UUID(requirement.indicator_id)
            geography_id = UUID(alternative.identifier)
        except ValueError:
            return EvidenceResolution(
                status=EvidenceResolutionStatus.MISSING,
                detail="indicator and alternative identifiers must be UUIDs for the legacy adapter",
            )

        statement = (
            select(DataPoint, Indicator, Dataset, Province, District)
            .join(Indicator, DataPoint.indicator_id == Indicator.id)
            .join(Dataset, DataPoint.dataset_id == Dataset.id)
            .outerjoin(Province, DataPoint.province_id == Province.id)
            .outerjoin(District, DataPoint.district_id == District.id)
            .where(DataPoint.indicator_id == indicator_id)
        )
        if actual_level is GeographicLevel.DISTRICT:
            statement = statement.where(DataPoint.district_id == geography_id)
        elif actual_level is GeographicLevel.PROVINCE:
            statement = statement.where(DataPoint.province_id == geography_id)
        else:
            return EvidenceResolution(
                status=EvidenceResolutionStatus.GEOGRAPHICALLY_INCOMPATIBLE,
                detail="legacy adapter supports province and district observations only",
            )

        rows = list((await self._session.execute(statement)).all())
        if not rows:
            return EvidenceResolution(
                status=(
                    EvidenceResolutionStatus.TEMPORALLY_INCOMPATIBLE
                    if request.reference_year is not None
                    and await self._has_other_period(indicator_id, geography_id, actual_level)
                    else EvidenceResolutionStatus.MISSING
                ),
                detail="no observation satisfies the requested indicator and geography",
            )

        if request.reference_year is not None:
            exact_rows = [row for row in rows if row[0].reference_year == request.reference_year]
            if not exact_rows:
                return EvidenceResolution(
                    status=EvidenceResolutionStatus.TEMPORALLY_INCOMPATIBLE,
                    detail="observations exist, but none match the requested reference year",
                )
            rows = exact_rows

        rows.sort(
            key=lambda row: (
                -row[0].reference_year,
                -(row[2].updated_at.timestamp() if row[2].updated_at else 0),
                str(row[2].id),
                str(row[0].id),
            )
        )
        point, indicator, dataset, province, district = rows[0]
        freshness_date = dataset.updated_at.date() if dataset.updated_at else None
        freshness_status = self._freshness_status(
            freshness_date, request.max_evidence_age_days, as_of or date.today()
        )
        if freshness_status is FreshnessStatus.STALE and request.max_evidence_age_days is not None:
            return EvidenceResolution(
                status=EvidenceResolutionStatus.STALE,
                detail="best matching evidence exceeds the requested freshness age",
            )

        evidence = Evidence(
            indicator_id=str(indicator.id),
            indicator_name=indicator.name,
            raw_value=float(point.value),
            unit=indicator.unit,
            geography_id=str(district.id if district is not None else province.id),
            geography_name=district.name if district is not None else province.name,
            geographic_level=(
                GeographicLevel.DISTRICT if district is not None else GeographicLevel.PROVINCE
            ),
            reference_year=point.reference_year,
            dataset_id=str(dataset.id),
            dataset_name=dataset.name,
            source_institution=dataset.source_name,
            source_reference=dataset.source_url,
            publication_date=None,
            freshness_date=freshness_date,
            quality=EvidenceQuality.UNKNOWN,
            freshness_status=freshness_status,
        )
        return EvidenceResolution(status=EvidenceResolutionStatus.RESOLVED, evidence=evidence)

    async def _has_other_period(
        self, indicator_id: UUID, geography_id: UUID, level: GeographicLevel | None
    ) -> bool:
        statement = select(DataPoint.id).where(DataPoint.indicator_id == indicator_id)
        if level is GeographicLevel.DISTRICT:
            statement = statement.where(DataPoint.district_id == geography_id)
        else:
            statement = statement.where(DataPoint.province_id == geography_id)
        return (await self._session.execute(statement)).first() is not None

    @staticmethod
    def _alternative_level(alternative: DecisionAlternative) -> GeographicLevel | None:
        try:
            return GeographicLevel(alternative.alternative_type.lower())
        except ValueError:
            return None

    @staticmethod
    def _freshness_status(
        freshness_date: date | None, max_age_days: int | None, as_of: date
    ) -> FreshnessStatus:
        if freshness_date is None:
            return FreshnessStatus.UNKNOWN
        if max_age_days is not None and (as_of - freshness_date).days > max_age_days:
            return FreshnessStatus.STALE
        return FreshnessStatus.CURRENT
