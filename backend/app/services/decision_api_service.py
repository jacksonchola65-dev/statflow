from __future__ import annotations

from app.domain.decision import (
    BusinessLocationMode,
    BusinessLocationRequest,
    DecisionAlternative,
    DecisionRequest,
    GeographicLevel,
    IndicatorRequirement,
    build_business_location_definition,
    build_business_location_evidence_portfolio,
    build_business_location_run,
    get_business_category_profile,
)
from app.domain.decision.resolver import EvidenceResolutionStatus
from app.models.indicator import Indicator
from app.models.province import Province
from app.repositories.district_repository import DistrictRepository
from app.services.decision_evidence import DecisionEvidenceResolver
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


class DecisionApiService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def evaluate(
        self,
        *,
        model_id: str,
        province_code: str,
        mode: BusinessLocationMode,
        business_category: str,
        reference_year: int | None,
        criterion_weights: dict[str, float],
    ) -> dict:
        if model_id != "BUSINESS_LOCATION_OPPORTUNITY":
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Decision model not found."
            )
        if criterion_weights:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Criterion weight overrides are not enabled for Decision API V1.",
            )
        try:
            profile = get_business_category_profile(business_category)
        except ValueError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
            ) from exc

        normalized_province = province_code.strip().upper()
        province = (
            await self._session.execute(
                select(Province).where(Province.code == normalized_province)
            )
        ).scalar_one_or_none()
        if province is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Unsupported province."
            )

        districts = await DistrictRepository(self._session).get_districts_by_province(province.id)
        if not districts:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="No canonical districts found for province.",
            )
        alternatives = tuple(
            DecisionAlternative(
                identifier=str(district.id),
                display_name=district.name,
                alternative_type="district",
                metadata={"code": district.code, "province_code": province.code},
            )
            for district in districts
        )
        indicator = (
            await self._session.execute(select(Indicator).where(Indicator.code == "POP_TOTAL"))
        ).scalar_one_or_none()
        if indicator is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Market Demand indicator is unavailable.",
            )

        decision_request = DecisionRequest(
            decision_definition_id="BUSINESS_LOCATION_OPPORTUNITY",
            original_question="Business Location Opportunity evaluation",
            business_category=profile.category_id,
            geographic_scope=province.code,
            reference_year=reference_year,
            decision_constraints={"require_provenance": True},
        )
        requirement = IndicatorRequirement(
            indicator_id=str(indicator.id),
            name=indicator.name,
            geographic_level=GeographicLevel.DISTRICT,
        )
        resolver = DecisionEvidenceResolver(self._session)
        resolution_items = []
        for alternative in alternatives:
            resolution_items.append(
                await resolver.resolve(requirement, alternative, decision_request)
            )
        resolutions = tuple(resolution_items)
        failed = tuple(
            item for item in resolutions if item.status is not EvidenceResolutionStatus.RESOLVED
        )
        if failed and mode is BusinessLocationMode.EXPLORATORY:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="Market Demand evidence could not be resolved for all districts.",
            )
        evidence = tuple(item.evidence for item in resolutions if item.evidence is not None)
        criterion_evidence = tuple(
            item.model_copy(update={"indicator_id": "market_demand"}) for item in evidence
        )
        result = build_business_location_run(
            BusinessLocationRequest(
                business_category=profile.category_id,
                province_code=province.code,
                original_question="Business Location Opportunity evaluation",
                reference_year=reference_year,
                mode=mode,
            ),
            alternatives,
            criterion_evidence,
        )
        decision = result.decision
        portfolio = result.evidence_portfolio
        return {
            "run_id": f"{result.decision.methodology_version}:{province.code}:{reference_year}:{mode.value}",
            "model_id": result.decision.definition.identifier,
            "model_version": result.decision.definition.version,
            "mode": "EXPLORATORY" if mode is BusinessLocationMode.EXPLORATORY else "PRODUCTION",
            "exploratory_designation": (
                "NOT_A_PRODUCTION_RECOMMENDATION"
                if mode is BusinessLocationMode.EXPLORATORY
                else "PRODUCTION_DECISION"
            ),
            "persisted": False,
            "province": province.code,
            "decision_readiness": decision.readiness.state.value,
            "model_readiness_percentage": portfolio.readiness_percentage,
            "production_recommendation": mode is not BusinessLocationMode.EXPLORATORY
            and decision.recommendation is not None,
            "recommendation": decision.recommendation.model_dump(mode="json")
            if decision.recommendation
            else None,
            "candidates": tuple(item.model_dump(mode="json") for item in alternatives),
            "evidence": tuple(item.model_dump(mode="json") for item in criterion_evidence),
            "criterion_scores": tuple(
                item.model_dump(mode="json") for item in decision.criterion_scores
            ),
            "evidence_coverage": tuple(item.model_dump(mode="json") for item in decision.coverage),
            "criterion_readiness": tuple(
                item.model_dump(mode="json") for item in portfolio.criteria
            ),
            "confidence": decision.confidence.model_dump(mode="json"),
            "sensitivity": decision.sensitivity.model_dump(mode="json")
            if decision.sensitivity
            else None,
            "ties": decision.ties.model_dump(mode="json"),
            "blockers": tuple(
                item.criterion_id
                for item in portfolio.criteria
                if item.state.value != "production_usable"
            ),
            "blocker_reasons": tuple(
                {
                    "criterion_id": criterion_id,
                    "reasons": tuple(reason.value for reason in reasons),
                }
                for criterion_id, reasons in portfolio.blocking_reasons
            ),
            "limitations": (
                (
                    "This exploratory output is not a production-grade Business Location recommendation.",
                )
                if mode is BusinessLocationMode.EXPLORATORY
                else ()
            ),
            "explanation": decision.explanation.model_dump(mode="json")
            if decision.explanation
            else {},
            "evidence_backlog": tuple(item.model_dump(mode="json") for item in portfolio.backlog),
            "methodology_versions": {
                "decision": decision.methodology_version,
                "scoring": decision.scoring_methodology_version,
                "normalization": decision.normalization_methodology_version,
                "confidence": decision.confidence.methodology_version,
            },
        }


def model_summary(business_category: str = "GENERAL_RETAIL") -> dict:
    profile = get_business_category_profile(business_category)
    portfolio = build_business_location_evidence_portfolio(profile)
    definition = build_business_location_definition(profile)
    criteria = tuple(
        {
            "criterion_id": item.identifier,
            "name": item.name,
            "weight": item.weight,
            "direction": item.direction.value,
            "required": item.required,
            "evidence_requirement": item.indicator_requirements[0].model_dump(mode="json"),
            "readiness": next(
                readiness.state.value
                for readiness in portfolio.criteria
                if readiness.criterion_id == item.identifier
            ),
        }
        for item in definition.criteria
    )
    return {
        "model_id": definition.identifier,
        "version": definition.version,
        "name": definition.name,
        "description": definition.description,
        "geographic_level": definition.geographic_level.value,
        "supported_modes": ("PRODUCTION", "EXPLORATORY"),
        "supported_business_categories": ("GENERAL_RETAIL", "SUPERMARKET"),
        "readiness_percentage": portfolio.readiness_percentage,
        "production_ready": portfolio.production_ready,
        "criteria": criteria,
        "limitations": profile.limitations,
        "evidence_backlog": tuple(item.model_dump(mode="json") for item in portfolio.backlog),
        "methodology_versions": {
            "model": definition.version,
            "scoring": "weighted_sum-v1",
            "normalization": "min_max-v1",
            "confidence": "confidence-v1",
        },
    }
