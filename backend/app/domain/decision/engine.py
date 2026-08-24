from __future__ import annotations

from dataclasses import dataclass

from app.domain.decision.contracts import (
    AbstentionReasonCode,
    ConfidenceAssessment,
    ConfidenceBand,
    CriterionDirection,
    CriterionScore,
    DecisionDefinition,
    DecisionDomainError,
    DecisionExplanation,
    DecisionReadiness,
    DecisionReadinessAssessment,
    DecisionRequest,
    DecisionRun,
    DecisionScore,
    EligibilityState,
    EvidenceCoverage,
    EvidenceQuality,
    FreshnessStatus,
    Missingness,
    Recommendation,
    ScoringStrategy,
    SensitivityAssessment,
    SensitivityCase,
    TieAssessment,
    WeightDefinition,
    WeightingStrategy,
    WeightSource,
)


@dataclass(frozen=True)
class NormalizationResult:
    values: tuple[float, ...]


def min_max_normalize(
    values: tuple[float | int | None, ...],
    direction: CriterionDirection,
    *,
    constant_value: float = 1.0,
) -> NormalizationResult:
    if not values or any(value is None for value in values):
        raise DecisionDomainError("min-max normalization requires non-missing values")
    numeric = tuple(float(value) for value in values if value is not None)
    minimum = min(numeric)
    maximum = max(numeric)
    if minimum == maximum:
        normalized = tuple(constant_value for _ in numeric)
    else:
        span = maximum - minimum
        normalized = tuple(min(1.0, max(0.0, (value - minimum) / span)) for value in numeric)
    if direction is CriterionDirection.LOWER_IS_BETTER:
        normalized = tuple(1.0 - value for value in normalized)
    return NormalizationResult(values=normalized)


def build_weighting_strategy(
    definition: DecisionDefinition, request: DecisionRequest
) -> WeightingStrategy:
    overrides = request.criterion_weights
    known = {criterion.identifier for criterion in definition.criteria}
    if set(overrides) - known:
        raise DecisionDomainError("weight override references an unknown criterion")
    weights = tuple(
        WeightDefinition(
            criterion_id=criterion.identifier,
            weight=overrides.get(criterion.identifier, criterion.weight),
            source=(
                WeightSource.USER_OVERRIDE
                if criterion.identifier in overrides
                else WeightSource.MODEL_DEFAULT
            ),
            default_weight=criterion.weight,
            override_weight=overrides.get(criterion.identifier),
        )
        for criterion in definition.criteria
    )
    if not any(weight.weight > 0 for weight in weights):
        raise DecisionDomainError("effective weights must contain a positive value")
    return WeightingStrategy(name="decision_weights", version=definition.version, weights=weights)


def normalize_weights(strategy: WeightingStrategy) -> dict[str, float]:
    total = sum(weight.weight for weight in strategy.weights)
    if total <= 0:
        raise DecisionDomainError("total effective weight must be positive")
    return {weight.criterion_id: weight.weight / total for weight in strategy.weights}


def _coverage(definition, alternatives, evidence, weighting) -> tuple[EvidenceCoverage, ...]:
    by_key = {(item.geography_id, item.indicator_id): item for item in evidence}
    weights = {item.criterion_id: item.weight for item in weighting.weights}
    total = sum(weights.values())
    coverage = []
    for alternative in alternatives:
        if alternative.eligibility is EligibilityState.EXCLUDED:
            continue
        required: list[str] = []
        optional: list[str] = []
        missing: list[str] = []
        represented = 0.0
        for criterion in definition.criteria:
            requirement = (
                criterion.indicator_requirements[0] if criterion.indicator_requirements else None
            )
            item = requirement and by_key.get((alternative.identifier, requirement.indicator_id))
            present = (
                item is not None
                and item.raw_value is not None
                and item.missingness is not Missingness.MISSING
            )
            if present:
                represented += weights[criterion.identifier]
                (required if criterion.required else optional).append(criterion.identifier)
            else:
                missing.append(criterion.identifier)
        coverage.append(
            EvidenceCoverage(
                alternative_id=alternative.identifier,
                required_criteria_satisfied=tuple(required),
                optional_criteria_satisfied=tuple(optional),
                missing_criteria=tuple(missing),
                effective_weight_represented=represented / total,
                effective_weight_missing=max(0.0, total - represented) / total,
                evidence_coverage_percentage=represented / total * 100,
            )
        )
    return tuple(coverage)


def _comparability(definition, alternatives, evidence, request):
    eligible = tuple(item for item in alternatives if item.eligibility is EligibilityState.ELIGIBLE)
    reasons = []
    descriptions = []
    if len(eligible) < 2:
        reasons.append(AbstentionReasonCode.INSUFFICIENT_ELIGIBLE_ALTERNATIVES)
        descriptions.append("At least two eligible alternatives are required.")
    duplicate_keys = {
        key
        for key in {(item.geography_id, item.indicator_id) for item in evidence}
        if sum(1 for item in evidence if (item.geography_id, item.indicator_id) == key) > 1
    }
    if duplicate_keys:
        reasons.append(AbstentionReasonCode.DUPLICATE_EVIDENCE)
        descriptions.append("Duplicate evidence exists for one or more alternative indicators.")
    for criterion in definition.criteria:
        requirement = (
            criterion.indicator_requirements[0] if criterion.indicator_requirements else None
        )
        if requirement is None:
            continue
        items = [item for item in evidence if item.indicator_id == requirement.indicator_id]
        present_items = [item for item in items if item.raw_value is not None]
        if (
            request.decision_constraints.get("require_provenance", False)
            and criterion.required
            and any(
                not item.source_institution or not item.source_reference for item in present_items
            )
        ):
            reasons.append(AbstentionReasonCode.INCOMPLETE_PROVENANCE)
            descriptions.append(
                f"Required evidence has incomplete provenance for criterion {criterion.identifier}."
            )
        units = {item.unit for item in present_items if item.unit is not None}
        levels = {
            item.geographic_level for item in present_items if item.geographic_level is not None
        }
        periods = {item.reference_year for item in present_items if item.reference_year is not None}
        if len(units) > 1:
            reasons.append(AbstentionReasonCode.INCOMPARABLE_UNITS)
            descriptions.append(f"Criterion {criterion.identifier} has inconsistent units.")
        target_level = requirement.geographic_level or definition.geographic_level
        if levels and levels - {target_level}:
            reasons.append(AbstentionReasonCode.INCOMPARABLE_GEOGRAPHIES)
            descriptions.append(
                f"Criterion {criterion.identifier} has incompatible geography levels."
            )
        if request.reference_year is not None and periods and periods != {request.reference_year}:
            reasons.append(AbstentionReasonCode.INCOMPARABLE_PERIODS)
            descriptions.append(
                f"Criterion {criterion.identifier} has incompatible reference periods."
            )
        if criterion.required and len([item for item in items if item.raw_value is not None]) < len(
            eligible
        ):
            reasons.append(AbstentionReasonCode.INSUFFICIENT_REQUIRED_EVIDENCE)
            descriptions.append(
                f"Required evidence is missing for criterion {criterion.identifier}."
            )
        if request.max_evidence_age_days and any(
            item.freshness_status is FreshnessStatus.STALE for item in items
        ):
            reasons.append(AbstentionReasonCode.STALE_REQUIRED_EVIDENCE)
            descriptions.append(f"Required evidence is stale for criterion {criterion.identifier}.")
    unique = tuple(dict.fromkeys(reasons))
    return not unique, unique, tuple(dict.fromkeys(descriptions))


def _score_once(definition, request, alternatives, evidence) -> tuple[DecisionScore, ...]:
    weighting = build_weighting_strategy(definition, request)
    by_key = {(item.geography_id, item.indicator_id): item for item in evidence}
    scores = []
    for alternative in alternatives:
        if alternative.eligibility is EligibilityState.EXCLUDED:
            continue
        components = []
        for criterion in definition.criteria:
            requirement = (
                criterion.indicator_requirements[0] if criterion.indicator_requirements else None
            )
            item = requirement and by_key.get((alternative.identifier, requirement.indicator_id))
            if item is None or item.raw_value is None:
                if criterion.required:
                    raise DecisionDomainError(
                        f"required evidence missing for {alternative.identifier}/{criterion.identifier}"
                    )
                continue
            weight = next(
                weight
                for weight in weighting.weights
                if weight.criterion_id == criterion.identifier
            )
            components.append((criterion, item, weight))
        if not components:
            raise DecisionDomainError(
                f"no usable evidence for alternative {alternative.identifier}"
            )
        total = sum(item.weight for _, _, item in components)
        criterion_scores = []
        for criterion, item, weight in components:
            requirement = criterion.indicator_requirements[0]
            peers = tuple(
                candidate
                for candidate in alternatives
                if candidate.eligibility is EligibilityState.ELIGIBLE
                and (candidate.identifier, requirement.indicator_id) in by_key
                and by_key[(candidate.identifier, requirement.indicator_id)].raw_value is not None
            )
            values = tuple(
                by_key[(peer.identifier, requirement.indicator_id)].raw_value for peer in peers
            )
            normalized_values = min_max_normalize(
                values,
                criterion.direction,
                constant_value=criterion.normalization.constant_series_value,
            ).values
            normalized = normalized_values[
                next(
                    index
                    for index, peer in enumerate(peers)
                    if peer.identifier == alternative.identifier
                )
            ]
            effective = weight.weight / total
            criterion_scores.append(
                CriterionScore(
                    criterion_id=criterion.identifier,
                    evidence=item,
                    normalized_value=normalized,
                    effective_weight=effective,
                    weighted_contribution=normalized * effective,
                    default_weight=weight.default_weight or 0.0,
                    override_weight=weight.override_weight,
                )
            )
        scores.append(
            DecisionScore(
                alternative=alternative,
                criterion_scores=tuple(criterion_scores),
                final_score=sum(item.weighted_contribution for item in criterion_scores),
            )
        )
    return tuple(sorted(scores, key=lambda item: (-item.final_score, item.alternative.identifier)))


def score_alternatives(
    definition, request, alternatives, evidence, *, scoring_strategy=ScoringStrategy()
):
    if scoring_strategy.method.value != "weighted_sum":
        raise DecisionDomainError("unsupported scoring strategy")
    return _score_once(definition, request, alternatives, evidence)


def _confidence(coverage, evidence) -> ConfidenceAssessment:
    completeness = (
        sum(
            item.raw_value is not None and item.missingness is not Missingness.MISSING
            for item in evidence
        )
        / len(evidence)
        if evidence
        else 0.0
    )
    freshness = (
        sum(item.freshness_status is FreshnessStatus.CURRENT for item in evidence) / len(evidence)
        if evidence
        else 0.0
    )
    quality = (
        sum(item.quality is EvidenceQuality.VERIFIED for item in evidence) / len(evidence)
        if evidence
        else 0.0
    )
    score = (completeness + freshness + quality) / 3
    band = (
        ConfidenceBand.HIGH
        if score >= 0.8
        else ConfidenceBand.MEDIUM
        if score >= 0.5
        else ConfidenceBand.LOW
    )
    return ConfidenceAssessment(
        level=band.value,
        band=band,
        score=score,
        evidence_completeness=completeness,
        freshness=freshness,
        source_quality=quality,
        rationale="confidence-v1 averages evidence completeness, current freshness, and verified-source coverage",
        limitations=("This is evidence readiness, not probability of success.",),
    )


def _sensitivity(definition, request, alternatives, evidence, scores):
    base_leader = scores[0].alternative.identifier if scores else None
    cases, sensitive = [], []
    for criterion in definition.criteria:
        for perturbation in (-0.1, 0.1):
            overrides = dict(request.criterion_weights)
            base = overrides.get(criterion.identifier, criterion.weight)
            overrides[criterion.identifier] = base * (1 + perturbation)
            rerun = _score_once(
                definition,
                request.model_copy(update={"criterion_weights": overrides}),
                alternatives,
                evidence,
            )
            leader = rerun[0].alternative.identifier if rerun else None
            changed = leader != base_leader
            if changed:
                sensitive.append(criterion.identifier)
            cases.append(
                SensitivityCase(
                    criterion_id=criterion.identifier,
                    perturbation=perturbation,
                    leader_id=leader,
                    ranking=tuple(item.alternative.identifier for item in rerun),
                    leader_changed=changed,
                )
            )
    return SensitivityAssessment(
        stable_recommendation=not sensitive,
        sensitive_criteria=tuple(dict.fromkeys(sensitive)),
        cases=tuple(cases),
    )


def build_decision_run(
    definition, request, alternatives, evidence, *, confidence=None, explanation=None
):
    weighting = build_weighting_strategy(definition, request)
    coverage = _coverage(definition, alternatives, evidence, weighting)
    comparable, reasons, descriptions = _comparability(definition, alternatives, evidence, request)
    eligible_count = sum(item.eligibility is EligibilityState.ELIGIBLE for item in alternatives)
    required_complete = all(
        all(
            not next(
                criterion for criterion in definition.criteria if criterion.identifier == missing
            ).required
            for missing in item.missing_criteria
        )
        for item in coverage
    )
    if not required_complete:
        reasons = tuple(
            dict.fromkeys(reasons + (AbstentionReasonCode.INSUFFICIENT_CRITERION_COVERAGE,))
        )
        descriptions = tuple(
            dict.fromkeys(
                descriptions
                + ("Required criterion coverage is insufficient for a recommendation.",)
            )
        )
    ready = comparable and required_complete and eligible_count >= 2
    readiness = DecisionReadinessAssessment(
        state=DecisionReadiness.RECOMMENDATION_READY
        if ready
        else DecisionReadiness.INSUFFICIENT_EVIDENCE,
        reasons=() if ready else reasons,
        descriptions=() if ready else descriptions,
        comparable=comparable,
    )
    scores = _score_once(definition, request, alternatives, evidence) if ready else ()
    confidence_value = (
        confidence
        if isinstance(confidence, ConfidenceAssessment)
        else _confidence(coverage, evidence)
    )
    max_score = scores[0].final_score if scores else None
    tied = tuple(
        item.alternative.identifier
        for item in scores
        if max_score is not None and item.final_score == max_score
    )
    ties = TieAssessment(
        tied_leader_ids=tied if len(tied) > 1 else (),
        display_order=tuple(item.alternative.identifier for item in scores),
    )
    sensitivity = (
        _sensitivity(definition, request, alternatives, evidence, scores) if scores else None
    )
    recommendation = (
        Recommendation(
            alternative=scores[0].alternative,
            score=scores[0],
            confidence=confidence_value,
            tied_alternatives=tuple(
                item.alternative for item in scores if item.final_score == max_score
            ),
        )
        if scores
        else None
    )
    if explanation is None:
        winner_detail = "No recommendation was produced."
        if scores:
            winner = scores[0]
            components = "; ".join(
                f"{component.criterion_id} raw={component.evidence.raw_value} "
                f"normalized={component.normalized_value:.6f} "
                f"effective_weight={component.effective_weight:.6f} "
                f"contribution={component.weighted_contribution:.6f}"
                for component in winner.criterion_scores
            )
            winner_detail = (
                f"{winner.alternative.display_name} ranked first with the highest "
                f"decomposed final score "
                f"{winner.final_score:.6f}; {components}."
            )
        explanation = DecisionExplanation(
            methodology_reference="weighted_sum-v1",
            why_winner_ranked_first=winner_detail,
            missing_evidence=tuple(
                item.alternative_id for item in coverage if item.missing_criteria
            ),
            tied_leaders=tied if len(tied) > 1 else (),
            sensitivity_factors=sensitivity.sensitive_criteria if sensitivity else (),
            limitations=("Recommendation requires comparable, sufficient evidence.",),
        )
    return DecisionRun(
        request=request,
        definition=definition,
        alternatives_considered=alternatives,
        excluded_alternatives=tuple(
            item for item in alternatives if item.eligibility is EligibilityState.EXCLUDED
        ),
        evidence_used=evidence,
        criterion_scores=scores,
        ranking=tuple(item.alternative.identifier for item in scores),
        confidence=confidence_value,
        recommendation=recommendation,
        explanation=explanation,
        methodology_version=definition.version,
        readiness=readiness,
        coverage=coverage,
        sensitivity=sensitivity,
        ties=ties,
        abstention_reason=reasons[0] if reasons else None,
    )
