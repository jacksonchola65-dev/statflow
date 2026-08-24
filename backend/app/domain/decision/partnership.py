from __future__ import annotations

from app.domain.decision.contracts import FrozenModel, GeographicLevel
from app.domain.decision.models.business_location import (
    BUSINESS_LOCATION_MODEL_ID,
    BusinessCategoryProfile,
    BusinessLocationEvidencePortfolio,
    CriterionReadinessState,
    ReadinessBlocker,
    build_business_location_evidence_portfolio,
)
from pydantic import Field


class EvidencePartnershipRequirement(FrozenModel):
    criterion_id: str
    decision_model_id: str
    business_categories: tuple[str, ...]
    title: str
    description: str
    required_geography: GeographicLevel
    preferred_geography: GeographicLevel
    coverage_requirement: str
    freshness_requirement: str
    temporal_requirement: str
    preferred_source_institution: str
    alternative_source_institutions: tuple[str, ...]
    authority_tier_required: str
    expected_data_format: str
    current_availability_state: CriterionReadinessState
    blocker_categories: tuple[ReadinessBlocker, ...]
    production_gate_condition: str
    limitations: tuple[str, ...]
    contact_status: str = "candidate partner; data access not confirmed"
    methodology_implications: str = "Evidence must remain comparable across all eligible districts."
    configured_weight: float = Field(gt=0.0)
    current_readiness_impact_percentage: float = Field(ge=0.0)
    projected_readiness_percentage: float = Field(ge=0.0, le=100.0)


class ReadinessScenario(FrozenModel):
    criterion_id: str
    current_readiness_percentage: float = Field(ge=0.0, le=100.0)
    projected_readiness_percentage: float = Field(ge=0.0, le=100.0)
    recommendation_allowed: bool = False
    note: str = (
        "This scenario changes readiness only; it does not fabricate evidence or a recommendation."
    )


_PARTNERSHIP_DETAILS: dict[str, dict[str, object]] = {
    "market_growth": {
        "title": "Boundary-compatible historical district population series",
        "description": "Comparable historical and current district population evidence for a defensible growth derivation.",
        "coverage": "All eligible districts",
        "freshness": "Current series with documented historical reference periods",
        "temporal": "Comparable historical and current observations",
        "preferred": "Zambia Statistics Agency / ZamStats",
        "alternatives": (),
        "format": "District-level tabular series with geography and reference year",
        "implications": "Any growth derivation must document boundary compatibility and versioned methodology.",
    },
    "purchasing_power": {
        "title": "Statistically reliable district consumption or income evidence",
        "description": "District-compatible household consumption or income measures with survey quality metadata.",
        "coverage": "All eligible districts",
        "freshness": "Latest available survey within the documented production freshness policy",
        "temporal": "Reference period and survey wave must be explicit",
        "preferred": "Zambia Statistics Agency / ZamStats",
        "alternatives": (),
        "format": "District-level survey or administrative data with reliability metadata",
        "implications": "Province-level measures cannot be copied to districts.",
    },
    "accessibility": {
        "title": "District-complete authoritative accessibility evidence",
        "description": "Road, travel-time, or comparable accessibility evidence aligned to district geography.",
        "coverage": "All eligible districts",
        "freshness": "Current network or travel-time reference, with observation date",
        "temporal": "Reference date and aggregation period must be explicit",
        "preferred": "Road Development Agency",
        "alternatives": ("Ministry of Transport and Logistics", "ZICTA"),
        "format": "District-level GIS or tabular accessibility metric with provenance",
        "implications": "Derived metrics require district geometry, aggregation, and GIS lineage.",
    },
    "competition": {
        "title": "Category-specific active operating-establishment evidence",
        "description": "Active supermarket or grocery operating establishments matched to district and category.",
        "coverage": "All 12 eligible Luapula districts",
        "freshness": "No older than 2 years from the assessment date",
        "temporal": "Active status and reference date required",
        "preferred": "PACRA",
        "alternatives": ("Local councils", "Zambia Statistics Agency / ZamStats"),
        "format": "Structured establishment records with location, category, and active status",
        "implications": "Legal registration does not necessarily equal an operating outlet.",
    },
    "operating_feasibility": {
        "title": "District-complete infrastructure and reliability evidence",
        "description": "Electricity, water, connectivity, and commercial infrastructure evidence aligned to district service areas.",
        "coverage": "All eligible districts",
        "freshness": "Current service and reliability observations with dates",
        "temporal": "Reference date and reliability observation period must be explicit",
        "preferred": "ZESCO",
        "alternatives": (
            "Energy Regulation Board",
            "NWASCO / Luapula Water",
            "ZICTA",
            "Local councils",
        ),
        "format": "District-level service and reliability measures with source lineage",
        "implications": "Access without service reliability is insufficient for production feasibility.",
    },
}


def build_partnership_requirements(
    profile: BusinessCategoryProfile,
    portfolio: BusinessLocationEvidencePortfolio | None = None,
) -> tuple[EvidencePartnershipRequirement, ...]:
    current = portfolio or build_business_location_evidence_portfolio(profile)
    total_weight = sum(item.configured_weight for item in current.criteria)
    requirements: list[EvidencePartnershipRequirement] = []
    for item in current.criteria:
        if item.state is CriterionReadinessState.PRODUCTION_USABLE:
            continue
        detail = _PARTNERSHIP_DETAILS[item.criterion_id]
        projected = current.readiness_percentage + item.configured_weight / total_weight * 100
        requirements.append(
            EvidencePartnershipRequirement(
                criterion_id=item.criterion_id,
                decision_model_id=BUSINESS_LOCATION_MODEL_ID,
                business_categories=(profile.category_id,),
                title=detail["title"],
                description=detail["description"],
                required_geography=GeographicLevel.DISTRICT,
                preferred_geography=GeographicLevel.DISTRICT,
                coverage_requirement=detail["coverage"],
                freshness_requirement=detail["freshness"],
                temporal_requirement=detail["temporal"],
                preferred_source_institution=detail["preferred"],
                alternative_source_institutions=detail["alternatives"],
                authority_tier_required="TIER_1_OFFICIAL or documented equivalent",
                expected_data_format=detail["format"],
                current_availability_state=item.state,
                blocker_categories=item.blockers,
                production_gate_condition="All eligible districts must have comparable, authoritative, usable evidence.",
                limitations=item.limitations + (detail["implications"],),
                configured_weight=item.configured_weight,
                current_readiness_impact_percentage=item.configured_weight / total_weight * 100,
                projected_readiness_percentage=projected,
            )
        )
    return tuple(
        sorted(requirements, key=lambda item: (-item.configured_weight, item.criterion_id))
    )


def partnership_requirements_for_partner(
    profile: BusinessCategoryProfile, partner: str
) -> tuple[EvidencePartnershipRequirement, ...]:
    normalized = partner.strip().casefold()
    return tuple(
        item
        for item in build_partnership_requirements(profile)
        if normalized in item.preferred_source_institution.casefold()
        or any(
            normalized in alternative.casefold()
            for alternative in item.alternative_source_institutions
        )
    )


def readiness_scenario(profile: BusinessCategoryProfile, criterion_id: str) -> ReadinessScenario:
    portfolio = build_business_location_evidence_portfolio(profile)
    requirement = next(
        (
            item
            for item in build_partnership_requirements(profile, portfolio)
            if item.criterion_id == criterion_id
        ),
        None,
    )
    if requirement is None:
        raise ValueError(f"criterion is not blocked or is unknown: {criterion_id}")
    return ReadinessScenario(
        criterion_id=criterion_id,
        current_readiness_percentage=portfolio.readiness_percentage,
        projected_readiness_percentage=requirement.projected_readiness_percentage,
    )
