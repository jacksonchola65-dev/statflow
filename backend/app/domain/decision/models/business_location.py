from __future__ import annotations

from enum import Enum
from typing import Iterable

from app.domain.decision.contracts import (
    AbstentionReasonCode,
    CriterionDirection,
    DecisionAlternative,
    DecisionCriterion,
    DecisionDefinition,
    DecisionReadiness,
    DecisionRequest,
    DecisionRun,
    FrozenModel,
    GeographicLevel,
    IndicatorRequirement,
)
from app.domain.decision.engine import build_decision_run
from pydantic import Field, model_validator

BUSINESS_LOCATION_MODEL_ID = "BUSINESS_LOCATION_OPPORTUNITY"
BUSINESS_LOCATION_MODEL_VERSION = "business-location-v1"


class BusinessLocationMode(str, Enum):
    DECISION_READY = "decision_ready"
    EXPLORATORY = "exploratory"


class CriterionReadinessState(str, Enum):
    PRODUCTION_USABLE = "production_usable"
    EXPLORATORY_ONLY = "exploratory_only"
    INSUFFICIENT = "insufficient"
    BLOCKED_BY_EVIDENCE = "blocked_by_evidence"


class ReadinessBlocker(str, Enum):
    MISSING_DATA = "missing_data"
    WRONG_GEOGRAPHY = "wrong_geography"
    BOUNDARY_INCOMPATIBILITY = "boundary_incompatibility"
    INSUFFICIENT_STATISTICAL_RELIABILITY = "insufficient_statistical_reliability"
    NO_DISTRICT_COVERAGE = "no_district_coverage"
    STALE_EVIDENCE = "stale_evidence"
    UNRESOLVED_CONFLICT = "unresolved_conflict"
    MISSING_PROVENANCE = "missing_provenance"
    MISSING_OPERATING_LOCATION = "missing_operating_location"
    SERVICE_AREA_MISMATCH = "service_area_mismatch"
    UNSUPPORTED_DERIVATION = "unsupported_derivation"


class EvidenceBacklogItem(FrozenModel):
    criterion_id: str
    requirement: str
    preferred_geography: GeographicLevel
    preferred_source_type: str
    freshness_requirement: str
    production_gate: str
    partner_map: tuple[str, ...]


class CriterionReadiness(FrozenModel):
    criterion_id: str
    configured_weight: float = Field(gt=0.0)
    state: CriterionReadinessState
    evidence_coverage_percentage: float = Field(ge=0.0, le=100.0)
    geography_coverage_percentage: float = Field(ge=0.0, le=100.0)
    freshness_status: str
    source_authority: str
    blockers: tuple[ReadinessBlocker, ...] = ()
    required_future_evidence: tuple[str, ...] = ()
    partner_map: tuple[str, ...] = ()
    limitations: tuple[str, ...] = ()
    assessment_version: str = "business-location-evidence-portfolio-v1"


class BusinessLocationEvidencePortfolio(FrozenModel):
    model_id: str
    model_version: str
    criteria: tuple[CriterionReadiness, ...]
    backlog: tuple[EvidenceBacklogItem, ...] = ()
    exploratory_disclaimer: str = (
        "Exploratory output is not a production business location recommendation."
    )

    @model_validator(mode="after")
    def validate_criteria(self) -> "BusinessLocationEvidencePortfolio":
        expected = {
            "market_demand",
            "market_growth",
            "purchasing_power",
            "accessibility",
            "competition",
            "operating_feasibility",
        }
        actual = {item.criterion_id for item in self.criteria}
        if actual != expected or len(actual) != len(self.criteria):
            raise ValueError("business location portfolio must contain exactly six criteria")
        return self

    @property
    def production_ready(self) -> bool:
        return all(
            item.state is CriterionReadinessState.PRODUCTION_USABLE for item in self.criteria
        )

    @property
    def readiness_percentage(self) -> float:
        total = sum(item.configured_weight for item in self.criteria)
        usable = sum(
            item.configured_weight
            for item in self.criteria
            if item.state is CriterionReadinessState.PRODUCTION_USABLE
        )
        return usable / total * 100

    @property
    def blocking_criteria(self) -> tuple[str, ...]:
        return tuple(
            item.criterion_id
            for item in self.criteria
            if item.state is not CriterionReadinessState.PRODUCTION_USABLE
        )

    @property
    def blocking_reasons(self) -> tuple[tuple[str, tuple[ReadinessBlocker, ...]], ...]:
        return tuple(
            (item.criterion_id, item.blockers)
            for item in self.criteria
            if item.state is not CriterionReadinessState.PRODUCTION_USABLE
        )


_CURRENT_EVIDENCE_POLICY: dict[str, dict[str, object]] = {
    "market_demand": {
        "state": CriterionReadinessState.PRODUCTION_USABLE,
        "coverage": 100.0,
        "freshness": "current",
        "authority": "TIER_1_OFFICIAL",
        "blockers": (),
        "future": (),
        "limitations": (),
        "partner": ("Zambia Statistics Agency / ZamStats",),
        "requirement": "Authoritative 2022 district population evidence for all eligible districts.",
    },
    "market_growth": {
        "state": CriterionReadinessState.BLOCKED_BY_EVIDENCE,
        "coverage": 0.0,
        "freshness": "not_assessed",
        "authority": "TIER_1_OFFICIAL unavailable",
        "blockers": (
            ReadinessBlocker.BOUNDARY_INCOMPATIBILITY,
            ReadinessBlocker.NO_DISTRICT_COVERAGE,
            ReadinessBlocker.UNSUPPORTED_DERIVATION,
        ),
        "future": ("Boundary-compatible historical district population series.",),
        "limitations": ("Population growth is only a proxy for market growth.",),
        "partner": ("Zambia Statistics Agency / ZamStats",),
        "requirement": "Comparable historical and current district population evidence with versioned derivation.",
    },
    "purchasing_power": {
        "state": CriterionReadinessState.BLOCKED_BY_EVIDENCE,
        "coverage": 0.0,
        "freshness": "not_assessed",
        "authority": "TIER_1_OFFICIAL unavailable",
        "blockers": (
            ReadinessBlocker.NO_DISTRICT_COVERAGE,
            ReadinessBlocker.INSUFFICIENT_STATISTICAL_RELIABILITY,
        ),
        "future": ("Statistically reliable district household consumption or income evidence.",),
        "limitations": ("Province-level survey measures cannot be copied to districts.",),
        "partner": ("Zambia Statistics Agency / ZamStats",),
        "requirement": "District-compatible household purchasing-power evidence with survey quality metadata.",
    },
    "accessibility": {
        "state": CriterionReadinessState.BLOCKED_BY_EVIDENCE,
        "coverage": 0.0,
        "freshness": "not_assessed",
        "authority": "TIER_1_OFFICIAL unavailable",
        "blockers": (
            ReadinessBlocker.NO_DISTRICT_COVERAGE,
            ReadinessBlocker.MISSING_PROVENANCE,
        ),
        "future": ("District-compatible road or travel-time accessibility metric.",),
        "limitations": ("A future derived metric requires district geometry and GIS lineage.",),
        "partner": ("Road Development Agency", "Ministry of Transport", "ZICTA"),
        "requirement": "Current district-complete physical accessibility evidence with explicit aggregation.",
    },
    "competition": {
        "state": CriterionReadinessState.BLOCKED_BY_EVIDENCE,
        "coverage": 0.0,
        "freshness": "not_assessed",
        "authority": "TIER_1_OFFICIAL unavailable",
        "blockers": (
            ReadinessBlocker.NO_DISTRICT_COVERAGE,
            ReadinessBlocker.MISSING_OPERATING_LOCATION,
        ),
        "future": ("Category-specific active operating-establishment evidence.",),
        "limitations": ("Formal registration does not capture all informal competition.",),
        "partner": ("PACRA", "Local councils", "Zambia Statistics Agency / ZamStats"),
        "requirement": "Current category-relevant district outlet evidence with active status and deduplication.",
    },
    "operating_feasibility": {
        "state": CriterionReadinessState.BLOCKED_BY_EVIDENCE,
        "coverage": 0.0,
        "freshness": "not_assessed",
        "authority": "TIER_1_OFFICIAL unavailable",
        "blockers": (
            ReadinessBlocker.NO_DISTRICT_COVERAGE,
            ReadinessBlocker.SERVICE_AREA_MISMATCH,
        ),
        "future": (
            "District-compatible electricity, water, connectivity, and commercial infrastructure evidence.",
        ),
        "limitations": (
            "Electricity access without reliability is insufficient for production feasibility.",
        ),
        "partner": ("ZESCO", "ERB", "NWASCO", "ZICTA", "Local councils"),
        "requirement": "District-complete infrastructure evidence with service-area alignment and reliability measures.",
    },
}


def build_business_location_evidence_portfolio(
    profile: BusinessCategoryProfile,
    *,
    readiness_policy: dict[str, dict[str, object]] | None = None,
    alternatives: Iterable[DecisionAlternative] | None = None,
    evidence: Iterable | None = None,
) -> BusinessLocationEvidencePortfolio:
    policy = readiness_policy or _CURRENT_EVIDENCE_POLICY
    definition = build_business_location_definition(profile)
    assessed_policy = {criterion_id: dict(values) for criterion_id, values in policy.items()}
    if readiness_policy is None and alternatives is not None and evidence is not None:
        eligible_ids = {
            item.identifier for item in alternatives if item.eligibility.value == "eligible"
        }
        evidence_by_criterion = {
            criterion_id: {
                item.geography_id
                for item in evidence
                if item.indicator_id == criterion_id
                and item.raw_value is not None
                and item.missingness.value != "missing"
            }
            for criterion_id in assessed_policy
        }
        for criterion_id, geography_ids in evidence_by_criterion.items():
            if eligible_ids and eligible_ids <= geography_ids:
                assessed_policy[criterion_id].update(
                    state=CriterionReadinessState.PRODUCTION_USABLE,
                    coverage=100.0,
                    freshness="current",
                    blockers=(),
                    future=(),
                )
    criteria = tuple(
        CriterionReadiness(
            criterion_id=criterion.identifier,
            configured_weight=criterion.weight,
            state=assessed_policy[criterion.identifier]["state"],
            evidence_coverage_percentage=assessed_policy[criterion.identifier]["coverage"],
            geography_coverage_percentage=assessed_policy[criterion.identifier]["coverage"],
            freshness_status=assessed_policy[criterion.identifier]["freshness"],
            source_authority=assessed_policy[criterion.identifier]["authority"],
            blockers=assessed_policy[criterion.identifier]["blockers"],
            required_future_evidence=assessed_policy[criterion.identifier]["future"],
            limitations=assessed_policy[criterion.identifier]["limitations"],
            partner_map=assessed_policy[criterion.identifier]["partner"],
        )
        for criterion in definition.criteria
    )
    backlog = tuple(
        EvidenceBacklogItem(
            criterion_id=item.criterion_id,
            requirement=assessed_policy.get(item.criterion_id, {}).get(
                "requirement", _CURRENT_EVIDENCE_POLICY[item.criterion_id]["requirement"]
            ),
            preferred_geography=GeographicLevel.DISTRICT,
            preferred_source_type="authoritative district-level evidence",
            freshness_requirement="criterion-specific documented freshness policy",
            production_gate="All eligible districts must have comparable, authoritative, usable evidence.",
            partner_map=item.partner_map,
        )
        for item in criteria
        if item.state is not CriterionReadinessState.PRODUCTION_USABLE
    )
    return BusinessLocationEvidencePortfolio(
        model_id=BUSINESS_LOCATION_MODEL_ID,
        model_version=BUSINESS_LOCATION_MODEL_VERSION,
        criteria=criteria,
        backlog=backlog,
    )


class BusinessCategoryProfile(FrozenModel):
    category_id: str
    name: str
    criterion_weights: dict[str, float]
    weight_rationales: dict[str, str]
    limitations: tuple[str, ...] = ()


class BusinessLocationRequest(FrozenModel):
    business_category: str = Field(min_length=1)
    province_code: str = Field(min_length=1)
    original_question: str = Field(min_length=1)
    reference_year: int | None = None
    criterion_weights: dict[str, float] = Field(default_factory=dict)
    max_evidence_age_days: int | None = Field(default=None, gt=0)
    mode: BusinessLocationMode = BusinessLocationMode.DECISION_READY


class BusinessLocationResult(FrozenModel):
    business_category: str
    requested_province: str
    mode: BusinessLocationMode
    profile: BusinessCategoryProfile
    criteria_used: tuple[str, ...]
    criteria_unavailable: tuple[str, ...]
    decision: DecisionRun
    evidence_portfolio: BusinessLocationEvidencePortfolio


GENERAL_RETAIL = BusinessCategoryProfile(
    category_id="GENERAL_RETAIL",
    name="General retail",
    criterion_weights={
        "market_demand": 0.25,
        "market_growth": 0.15,
        "purchasing_power": 0.20,
        "accessibility": 0.15,
        "competition": 0.15,
        "operating_feasibility": 0.10,
    },
    weight_rationales={
        "market_demand": "Current demand is the primary market signal.",
        "market_growth": "Growth indicates future demand potential.",
        "purchasing_power": "Purchasing power indicates ability to support sales.",
        "accessibility": "Accessibility affects customer reach and logistics.",
        "competition": "Competition affects unmet demand and market pressure.",
        "operating_feasibility": "Operating feasibility captures practical execution constraints.",
    },
    limitations=("Weights are an initial model policy, not a production investment forecast.",),
)

SUPERMARKET = BusinessCategoryProfile(
    category_id="SUPERMARKET",
    name="Supermarket",
    criterion_weights={
        "market_demand": 0.25,
        "market_growth": 0.15,
        "purchasing_power": 0.20,
        "accessibility": 0.20,
        "competition": 0.15,
        "operating_feasibility": 0.05,
    },
    weight_rationales={
        "market_demand": "Household demand is the primary supermarket market signal.",
        "market_growth": "Population and market growth indicate future store demand.",
        "purchasing_power": "Purchasing power supports basket size and sales viability.",
        "accessibility": "Store access and logistics are material to supermarket performance.",
        "competition": "Existing competition affects whitespace and market pressure.",
        "operating_feasibility": "Operating feasibility remains relevant but is not yet fully measured.",
    },
    limitations=("Weights are an initial model policy, not a production investment forecast.",),
)

_PROFILES = {profile.category_id: profile for profile in (GENERAL_RETAIL, SUPERMARKET)}


def get_business_category_profile(category: str) -> BusinessCategoryProfile:
    normalized = category.strip().upper().replace("-", "_").replace(" ", "_")
    try:
        return _PROFILES[normalized]
    except KeyError as exc:
        raise ValueError(f"unsupported business category: {category}") from exc


def build_business_location_definition(
    profile: BusinessCategoryProfile,
    *,
    exploratory: bool = False,
) -> DecisionDefinition:
    required = not exploratory
    criteria = (
        ("market_demand", "Market demand", CriterionDirection.HIGHER_IS_BETTER),
        ("market_growth", "Market growth", CriterionDirection.HIGHER_IS_BETTER),
        ("purchasing_power", "Purchasing power", CriterionDirection.HIGHER_IS_BETTER),
        ("accessibility", "Accessibility", CriterionDirection.HIGHER_IS_BETTER),
        ("competition", "Competition", CriterionDirection.LOWER_IS_BETTER),
        ("operating_feasibility", "Operating feasibility", CriterionDirection.HIGHER_IS_BETTER),
    )
    return DecisionDefinition(
        identifier=BUSINESS_LOCATION_MODEL_ID,
        name="Business Location Opportunity Analysis",
        description=(
            "Versioned district-level comparison of business location opportunity "
            "using statistical evidence."
        ),
        version=BUSINESS_LOCATION_MODEL_VERSION,
        geographic_level=GeographicLevel.DISTRICT,
        criteria=tuple(
            DecisionCriterion(
                identifier=identifier,
                name=name,
                direction=direction,
                weight=profile.criterion_weights[identifier],
                required=required,
                indicator_requirements=(
                    IndicatorRequirement(
                        indicator_id=identifier,
                        name=name,
                        geographic_level=GeographicLevel.DISTRICT,
                    ),
                ),
            )
            for identifier, name, direction in criteria
        ),
        eligibility_rules=(
            "Only districts belonging to the requested province may be eligible candidates.",
            "Decision-ready output requires evidence for every model criterion.",
        ),
    )


def build_business_location_run(
    request: BusinessLocationRequest,
    alternatives: Iterable[DecisionAlternative],
    evidence: Iterable,
) -> BusinessLocationResult:
    profile = get_business_category_profile(request.business_category)
    exploratory = request.mode is BusinessLocationMode.EXPLORATORY
    definition = build_business_location_definition(profile, exploratory=exploratory)
    decision_request = DecisionRequest(
        decision_definition_id=definition.identifier,
        original_question=request.original_question,
        business_category=profile.category_id,
        geographic_scope=request.province_code,
        reference_year=request.reference_year,
        criterion_weights=request.criterion_weights,
        max_evidence_age_days=request.max_evidence_age_days,
        decision_constraints={"require_provenance": True},
    )
    candidate_tuple = tuple(alternatives)
    evidence_tuple = tuple(evidence)
    decision = build_decision_run(
        definition,
        decision_request,
        candidate_tuple,
        evidence_tuple,
    )
    portfolio = build_business_location_evidence_portfolio(
        profile,
        alternatives=candidate_tuple,
        evidence=evidence_tuple,
    )
    if not exploratory and not portfolio.production_ready and decision.recommendation is not None:
        decision = decision.model_copy(
            update={
                "criterion_scores": (),
                "ranking": (),
                "recommendation": None,
                "sensitivity": None,
                "ties": decision.ties.model_copy(update={"display_order": ()}),
                "readiness": decision.readiness.model_copy(
                    update={
                        "state": DecisionReadiness.INSUFFICIENT_EVIDENCE,
                        "reasons": tuple(
                            dict.fromkeys(
                                decision.readiness.reasons
                                + (AbstentionReasonCode.INSUFFICIENT_CRITERION_COVERAGE,)
                            )
                        ),
                    }
                ),
            }
        )
    engine_explanation = decision.explanation
    assert engine_explanation is not None
    decision = decision.model_copy(
        update={
            "explanation": engine_explanation.model_copy(
                update={
                    "methodology_reference": BUSINESS_LOCATION_MODEL_VERSION,
                    "why_winner_ranked_first": (
                        "The leading district has the highest decomposed weighted score."
                        if decision.recommendation is not None
                        else engine_explanation.why_winner_ranked_first
                    ),
                    "limitations": profile.limitations
                    + (
                        ("Exploratory output is not a production-grade recommendation.",)
                        if exploratory
                        else ()
                    ),
                }
            )
        }
    )
    available = {item.indicator_id for item in evidence_tuple if item.raw_value is not None}
    criteria = tuple(criterion.identifier for criterion in definition.criteria)
    return BusinessLocationResult(
        business_category=profile.category_id,
        requested_province=request.province_code,
        mode=request.mode,
        profile=profile,
        criteria_used=tuple(identifier for identifier in criteria if identifier in available),
        criteria_unavailable=tuple(
            identifier for identifier in criteria if identifier not in available
        ),
        decision=decision,
        evidence_portfolio=portfolio,
    )
