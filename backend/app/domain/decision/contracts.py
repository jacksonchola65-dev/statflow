from __future__ import annotations

from datetime import date
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


class DecisionDomainError(ValueError):
    """Base error for invalid decision-domain inputs."""


class GeographicLevel(str, Enum):
    COUNTRY = "country"
    PROVINCE = "province"
    DISTRICT = "district"
    CUSTOM = "custom"


class CriterionDirection(str, Enum):
    HIGHER_IS_BETTER = "higher_is_better"
    LOWER_IS_BETTER = "lower_is_better"


class Missingness(str, Enum):
    PRESENT = "present"
    MISSING = "missing"


class FreshnessStatus(str, Enum):
    CURRENT = "current"
    STALE = "stale"
    UNKNOWN = "unknown"


class DecisionReadiness(str, Enum):
    RECOMMENDATION_READY = "recommendation_ready"
    INSUFFICIENT_EVIDENCE = "insufficient_evidence"


class ConfidenceBand(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class AbstentionReasonCode(str, Enum):
    INSUFFICIENT_REQUIRED_EVIDENCE = "insufficient_required_evidence"
    INSUFFICIENT_ELIGIBLE_ALTERNATIVES = "insufficient_eligible_alternatives"
    INCOMPARABLE_UNITS = "incomparable_units"
    INCOMPARABLE_GEOGRAPHIES = "incomparable_geographies"
    INCOMPARABLE_PERIODS = "incomparable_periods"
    STALE_REQUIRED_EVIDENCE = "stale_required_evidence"
    INSUFFICIENT_CRITERION_COVERAGE = "insufficient_criterion_coverage"
    DUPLICATE_EVIDENCE = "duplicate_evidence"
    INCOMPLETE_PROVENANCE = "incomplete_provenance"


class EvidenceQuality(str, Enum):
    UNKNOWN = "unknown"
    UNVERIFIED = "unverified"
    VERIFIED = "verified"


class NormalizationMethod(str, Enum):
    MIN_MAX = "min_max"


class WeightSource(str, Enum):
    MODEL_DEFAULT = "model_default"
    USER_OVERRIDE = "user_override"


class ScoringMethod(str, Enum):
    WEIGHTED_SUM = "weighted_sum"


class EligibilityState(str, Enum):
    ELIGIBLE = "eligible"
    EXCLUDED = "excluded"


class FrozenModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class IndicatorRequirement(FrozenModel):
    indicator_id: str
    name: str
    description: str = ""
    required: bool = True
    unit: str | None = None
    geographic_level: GeographicLevel | None = None


class NormalizationDefinition(FrozenModel):
    method: NormalizationMethod = NormalizationMethod.MIN_MAX
    constant_series_value: float = Field(default=1.0, ge=0.0, le=1.0)


class DecisionCriterion(FrozenModel):
    identifier: str
    name: str
    description: str = ""
    direction: CriterionDirection
    weight: float = Field(gt=0.0)
    required: bool = True
    indicator_requirements: tuple[IndicatorRequirement, ...] = ()
    normalization: NormalizationDefinition = NormalizationDefinition()


class DecisionDefinition(FrozenModel):
    identifier: str
    name: str
    description: str
    version: str
    geographic_level: GeographicLevel
    criteria: tuple[DecisionCriterion, ...] = Field(min_length=1)
    eligibility_rules: tuple[str, ...] = ()

    @model_validator(mode="after")
    def validate_criteria(self) -> "DecisionDefinition":
        identifiers = [criterion.identifier for criterion in self.criteria]
        if len(identifiers) != len(set(identifiers)):
            raise DecisionDomainError("decision criteria identifiers must be unique")
        return self


class DecisionRequest(FrozenModel):
    decision_definition_id: str
    original_question: str = Field(min_length=1)
    business_category: str | None = None
    geographic_scope: str | None = None
    reference_year: int | None = None
    candidate_constraints: dict[str, Any] = Field(default_factory=dict)
    criterion_weights: dict[str, float] = Field(default_factory=dict)
    max_evidence_age_days: int | None = Field(default=None, gt=0)
    decision_constraints: dict[str, Any] = Field(default_factory=dict)


class DecisionAlternative(FrozenModel):
    identifier: str
    display_name: str
    alternative_type: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    eligibility: EligibilityState = EligibilityState.ELIGIBLE
    exclusion_reasons: tuple[str, ...] = ()

    @model_validator(mode="after")
    def validate_exclusion(self) -> "DecisionAlternative":
        if self.eligibility is EligibilityState.EXCLUDED and not self.exclusion_reasons:
            raise DecisionDomainError("excluded alternatives require exclusion reasons")
        return self


class Evidence(FrozenModel):
    indicator_id: str
    indicator_name: str | None = None
    raw_value: float | int | None = None
    unit: str | None = None
    geography_id: str
    geography_name: str
    geographic_level: GeographicLevel | None = None
    reference_year: int | None = None
    reference_period: str | None = None
    dataset_id: str
    dataset_name: str | None = None
    dataset_version: str | None = None
    source_institution: str | None = None
    source_reference: str | None = None
    publication_date: date | None = None
    freshness_date: date | None = None
    quality: EvidenceQuality = EvidenceQuality.UNKNOWN
    missingness: Missingness = Missingness.PRESENT
    freshness_status: FreshnessStatus = FreshnessStatus.UNKNOWN

    @model_validator(mode="after")
    def validate_missingness(self) -> "Evidence":
        if self.missingness is Missingness.PRESENT and self.raw_value is None:
            raise DecisionDomainError("present evidence requires a raw value")
        if self.missingness is Missingness.MISSING and self.raw_value is not None:
            raise DecisionDomainError("missing evidence cannot contain a raw value")
        return self


class WeightDefinition(FrozenModel):
    criterion_id: str
    weight: float = Field(ge=0.0)
    source: WeightSource = WeightSource.MODEL_DEFAULT
    default_weight: float | None = Field(default=None, ge=0.0)
    override_weight: float | None = Field(default=None, ge=0.0)


class WeightingStrategy(FrozenModel):
    name: str
    version: str
    weights: tuple[WeightDefinition, ...]


class ScoringStrategy(FrozenModel):
    method: ScoringMethod = ScoringMethod.WEIGHTED_SUM
    version: str = "1"


class CriterionScore(FrozenModel):
    criterion_id: str
    evidence: Evidence
    normalized_value: float = Field(ge=0.0, le=1.0)
    effective_weight: float = Field(ge=0.0)
    weighted_contribution: float = Field(ge=0.0)
    default_weight: float = Field(ge=0.0)
    override_weight: float | None = Field(default=None, ge=0.0)


class DecisionScore(FrozenModel):
    alternative: DecisionAlternative
    criterion_scores: tuple[CriterionScore, ...]
    final_score: float = Field(ge=0.0, le=1.0)


class EvidenceCoverage(FrozenModel):
    alternative_id: str
    required_criteria_satisfied: tuple[str, ...] = ()
    optional_criteria_satisfied: tuple[str, ...] = ()
    missing_criteria: tuple[str, ...] = ()
    effective_weight_represented: float = Field(ge=0.0, le=1.0)
    effective_weight_missing: float = Field(ge=0.0, le=1.0)
    evidence_coverage_percentage: float = Field(ge=0.0, le=100.0)


class DecisionReadinessAssessment(FrozenModel):
    state: DecisionReadiness
    reasons: tuple[AbstentionReasonCode, ...] = ()
    descriptions: tuple[str, ...] = ()
    comparable: bool = True


class SensitivityCase(FrozenModel):
    criterion_id: str
    perturbation: float
    leader_id: str | None = None
    ranking: tuple[str, ...] = ()
    leader_changed: bool = False


class SensitivityAssessment(FrozenModel):
    perturbation_percentage: float = 10.0
    methodology_version: str = "local-weight-perturbation-v1"
    stable_recommendation: bool
    sensitive_criteria: tuple[str, ...] = ()
    cases: tuple[SensitivityCase, ...] = ()


class TieAssessment(FrozenModel):
    tied_leader_ids: tuple[str, ...] = ()
    display_order: tuple[str, ...] = ()


class ConfidenceAssessment(FrozenModel):
    level: str = "not_assessed"
    band: ConfidenceBand = ConfidenceBand.LOW
    score: float | None = Field(default=None, ge=0.0, le=1.0)
    evidence_completeness: float | None = Field(default=None, ge=0.0, le=1.0)
    freshness: float | None = Field(default=None, ge=0.0, le=1.0)
    source_quality: float | None = Field(default=None, ge=0.0, le=1.0)
    geographic_alignment: float | None = Field(default=None, ge=0.0, le=1.0)
    temporal_alignment: float | None = Field(default=None, ge=0.0, le=1.0)
    missing_data_penalty: float | None = Field(default=None, ge=0.0, le=1.0)
    sensitivity: float | None = Field(default=None, ge=0.0, le=1.0)
    rationale: str = "Confidence calculation not yet implemented."
    methodology_version: str = "confidence-v1"
    limitations: tuple[str, ...] = ()


class DecisionExplanation(FrozenModel):
    positive_factors: tuple[str, ...] = ()
    negative_factors: tuple[str, ...] = ()
    missing_evidence: tuple[str, ...] = ()
    assumptions: tuple[str, ...] = ()
    methodology_reference: str
    why_winner_ranked_first: str
    factors_that_could_change_recommendation: tuple[str, ...] = ()
    stale_evidence: tuple[str, ...] = ()
    tied_leaders: tuple[str, ...] = ()
    sensitivity_factors: tuple[str, ...] = ()
    limitations: tuple[str, ...] = ()


class Recommendation(FrozenModel):
    alternative: DecisionAlternative
    score: DecisionScore
    confidence: ConfidenceAssessment
    tied_alternatives: tuple[DecisionAlternative, ...] = ()


class DecisionRun(FrozenModel):
    request: DecisionRequest
    definition: DecisionDefinition
    alternatives_considered: tuple[DecisionAlternative, ...]
    excluded_alternatives: tuple[DecisionAlternative, ...] = ()
    evidence_used: tuple[Evidence, ...]
    criterion_scores: tuple[DecisionScore, ...]
    ranking: tuple[str, ...]
    confidence: ConfidenceAssessment
    recommendation: Recommendation | None = None
    explanation: DecisionExplanation | None = None
    methodology_version: str
    scoring_methodology_version: str = "weighted_sum-v1"
    normalization_methodology_version: str = "min_max-v1"
    readiness: DecisionReadinessAssessment = DecisionReadinessAssessment(
        state=DecisionReadiness.RECOMMENDATION_READY
    )
    coverage: tuple[EvidenceCoverage, ...] = ()
    sensitivity: SensitivityAssessment | None = None
    ties: TieAssessment = TieAssessment()
    abstention_reason: AbstentionReasonCode | None = None
