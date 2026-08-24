from __future__ import annotations

from datetime import date

import pytest
from app.domain.decision import (
    AbstentionReasonCode,
    ConfidenceAssessment,
    ConfidenceBand,
    CriterionDirection,
    DecisionAlternative,
    DecisionCriterion,
    DecisionDefinition,
    DecisionReadiness,
    DecisionRequest,
    Evidence,
    EvidenceQuality,
    FreshnessStatus,
    GeographicLevel,
    IndicatorRequirement,
    Missingness,
    WeightSource,
    build_decision_run,
    build_weighting_strategy,
    min_max_normalize,
    normalize_weights,
    score_alternatives,
)


def make_definition(
    *,
    demand_weight: float = 0.7,
    access_weight: float = 0.3,
    required_access: bool = True,
) -> DecisionDefinition:
    return DecisionDefinition(
        identifier="synthetic-decision-model",
        name="Synthetic growth decision",
        description="Maturity test model",
        version="decision-v1",
        geographic_level=GeographicLevel.DISTRICT,
        criteria=(
            DecisionCriterion(
                identifier="demand",
                name="Demand",
                direction=CriterionDirection.HIGHER_IS_BETTER,
                weight=demand_weight,
                required=True,
                indicator_requirements=(
                    IndicatorRequirement(indicator_id="demand", name="Demand"),
                ),
            ),
            DecisionCriterion(
                identifier="access",
                name="Access",
                direction=CriterionDirection.HIGHER_IS_BETTER,
                weight=access_weight,
                required=required_access,
                indicator_requirements=(
                    IndicatorRequirement(indicator_id="access", name="Access"),
                ),
            ),
        ),
    )


def make_alternatives() -> tuple[DecisionAlternative, ...]:
    return (
        DecisionAlternative(identifier="alpha", display_name="Alpha", alternative_type="district"),
        DecisionAlternative(identifier="beta", display_name="Beta", alternative_type="district"),
        DecisionAlternative(identifier="gamma", display_name="Gamma", alternative_type="district"),
    )


def make_request(**kwargs) -> DecisionRequest:
    payload = {
        "decision_definition_id": "synthetic-decision-model",
        "original_question": "Which option should be recommended?",
        "reference_year": 2025,
        "max_evidence_age_days": 365,
    }
    payload.update(kwargs)
    return DecisionRequest(**payload)


def make_evidence(
    *,
    values: dict[str, tuple[float | None, float | None]] | None = None,
    unit: str = "synthetic-units",
    freshness: FreshnessStatus = FreshnessStatus.CURRENT,
    quality: EvidenceQuality = EvidenceQuality.VERIFIED,
) -> tuple[Evidence, ...]:
    dataset = values or {"alpha": (60, 40), "beta": (80, 70), "gamma": (40, 10)}
    evidence: list[Evidence] = []
    for alternative, pair in dataset.items():
        for indicator, value in zip(("demand", "access"), pair):
            if value is None:
                evidence.append(
                    Evidence(
                        indicator_id=indicator,
                        raw_value=None,
                        unit=unit,
                        geography_id=alternative,
                        geography_name=alternative.title(),
                        geographic_level=GeographicLevel.DISTRICT,
                        reference_year=2025,
                        dataset_id=f"dataset-{alternative}-{indicator}",
                        dataset_name="synthetic dataset",
                        freshness_status=freshness,
                        quality=quality,
                        missingness=Missingness.MISSING,
                        publication_date=date(2025, 1, 15),
                        freshness_date=date(2025, 12, 31),
                    )
                )
            else:
                evidence.append(
                    Evidence(
                        indicator_id=indicator,
                        raw_value=value,
                        unit=unit,
                        geography_id=alternative,
                        geography_name=alternative.title(),
                        geographic_level=GeographicLevel.DISTRICT,
                        reference_year=2025,
                        dataset_id=f"dataset-{alternative}-{indicator}",
                        dataset_name="synthetic dataset",
                        freshness_status=freshness,
                        quality=quality,
                        missingness=Missingness.PRESENT,
                        publication_date=date(2025, 1, 15),
                        freshness_date=date(2025, 12, 31),
                    )
                )
    return tuple(evidence)


def test_readiness_reasons_are_exact_for_ready_and_abstaining_cases() -> None:
    definition = make_definition()
    request = make_request()
    alternatives = make_alternatives()

    ready = build_decision_run(definition, request, alternatives, make_evidence())
    assert ready.readiness.state is DecisionReadiness.RECOMMENDATION_READY
    assert ready.readiness.reasons == ()
    assert ready.recommendation is not None

    missing_access = build_decision_run(
        definition,
        request,
        alternatives,
        make_evidence(values={"alpha": (60, 40), "beta": (80, 70), "gamma": (40, None)}),
    )
    assert missing_access.readiness.state is DecisionReadiness.INSUFFICIENT_EVIDENCE
    assert AbstentionReasonCode.INSUFFICIENT_REQUIRED_EVIDENCE in missing_access.readiness.reasons
    assert AbstentionReasonCode.INSUFFICIENT_CRITERION_COVERAGE in missing_access.readiness.reasons
    assert missing_access.recommendation is None

    single = build_decision_run(definition, request, alternatives[:1], make_evidence())
    assert single.readiness.state is DecisionReadiness.INSUFFICIENT_EVIDENCE
    assert AbstentionReasonCode.INSUFFICIENT_ELIGIBLE_ALTERNATIVES in single.readiness.reasons

    stale_evidence = tuple(
        Evidence(
            **{
                **item.model_dump(),
                "freshness_status": FreshnessStatus.STALE,
                "freshness_date": date(2024, 1, 1),
            },
        )
        for item in make_evidence()
    )
    stale = build_decision_run(definition, request, alternatives, stale_evidence)
    assert stale.readiness.state is DecisionReadiness.INSUFFICIENT_EVIDENCE
    assert AbstentionReasonCode.STALE_REQUIRED_EVIDENCE in stale.readiness.reasons


def test_comparability_rejects_inconsistent_units_geographies_and_periods() -> None:
    definition = make_definition()
    request = make_request()
    alternatives = make_alternatives()

    unit_mismatch = build_decision_run(
        definition,
        request,
        alternatives,
        (
            Evidence(
                indicator_id="demand",
                raw_value=50,
                unit="units-a",
                geography_id="alpha",
                geography_name="Alpha",
                geographic_level=GeographicLevel.DISTRICT,
                reference_year=2025,
                dataset_id="alpha-demand-a",
                freshness_status=FreshnessStatus.CURRENT,
                quality=EvidenceQuality.VERIFIED,
                missingness=Missingness.PRESENT,
            ),
            Evidence(
                indicator_id="demand",
                raw_value=55,
                unit="units-b",
                geography_id="beta",
                geography_name="Beta",
                geographic_level=GeographicLevel.DISTRICT,
                reference_year=2025,
                dataset_id="beta-demand-b",
                freshness_status=FreshnessStatus.CURRENT,
                quality=EvidenceQuality.VERIFIED,
                missingness=Missingness.PRESENT,
            ),
            Evidence(
                indicator_id="demand",
                raw_value=60,
                unit="units-a",
                geography_id="gamma",
                geography_name="Gamma",
                geographic_level=GeographicLevel.DISTRICT,
                reference_year=2025,
                dataset_id="gamma-demand-a",
                freshness_status=FreshnessStatus.CURRENT,
                quality=EvidenceQuality.VERIFIED,
                missingness=Missingness.PRESENT,
            ),
            *[
                Evidence(
                    indicator_id="access",
                    raw_value=10,
                    unit="synthetic-units",
                    geography_id=item.identifier,
                    geography_name=item.display_name,
                    geographic_level=GeographicLevel.DISTRICT,
                    reference_year=2025,
                    dataset_id=f"access-{item.identifier}",
                    freshness_status=FreshnessStatus.CURRENT,
                    quality=EvidenceQuality.VERIFIED,
                    missingness=Missingness.PRESENT,
                )
                for item in alternatives
            ],
        ),
    )
    assert AbstentionReasonCode.INCOMPARABLE_UNITS in unit_mismatch.readiness.reasons
    assert unit_mismatch.recommendation is None

    geography_mismatch = build_decision_run(
        definition,
        request,
        alternatives,
        tuple(item for item in make_evidence() if item.indicator_id == "demand")
        + (
            Evidence(
                indicator_id="access",
                raw_value=10,
                unit="synthetic-units",
                geography_id="alpha",
                geography_name="Alpha",
                geographic_level=GeographicLevel.PROVINCE,
                reference_year=2025,
                dataset_id="access-alpha",
                freshness_status=FreshnessStatus.CURRENT,
                quality=EvidenceQuality.VERIFIED,
                missingness=Missingness.PRESENT,
            ),
            Evidence(
                indicator_id="access",
                raw_value=12,
                unit="synthetic-units",
                geography_id="beta",
                geography_name="Beta",
                geographic_level=GeographicLevel.PROVINCE,
                reference_year=2025,
                dataset_id="access-beta",
                freshness_status=FreshnessStatus.CURRENT,
                quality=EvidenceQuality.VERIFIED,
                missingness=Missingness.PRESENT,
            ),
            Evidence(
                indicator_id="access",
                raw_value=8,
                unit="synthetic-units",
                geography_id="gamma",
                geography_name="Gamma",
                geographic_level=GeographicLevel.PROVINCE,
                reference_year=2025,
                dataset_id="access-gamma",
                freshness_status=FreshnessStatus.CURRENT,
                quality=EvidenceQuality.VERIFIED,
                missingness=Missingness.PRESENT,
            ),
        ),
    )
    assert AbstentionReasonCode.INCOMPARABLE_GEOGRAPHIES in geography_mismatch.readiness.reasons
    assert geography_mismatch.recommendation is None

    period_mismatch = build_decision_run(
        definition,
        request,
        alternatives,
        tuple(
            Evidence(
                **{
                    **item.model_dump(),
                    "reference_year": 2024 if item.geography_id == "alpha" else 2025,
                }
            )
            for item in make_evidence()
        ),
    )
    assert AbstentionReasonCode.INCOMPARABLE_PERIODS in period_mismatch.readiness.reasons
    assert period_mismatch.recommendation is None

    valid = build_decision_run(definition, request, alternatives, make_evidence())
    assert valid.readiness.state is DecisionReadiness.RECOMMENDATION_READY
    assert valid.recommendation is not None
    assert valid.recommendation.alternative.identifier == "beta"


def test_coverage_maths_are_exact_for_required_and_missing_weights() -> None:
    definition = make_definition(demand_weight=0.7, access_weight=0.3)
    request = make_request()
    alternatives = make_alternatives()
    evidence = (
        Evidence(
            indicator_id="demand",
            raw_value=80,
            unit="synthetic-units",
            geography_id="alpha",
            geography_name="Alpha",
            geographic_level=GeographicLevel.DISTRICT,
            reference_year=2025,
            dataset_id="alpha-demand",
            freshness_status=FreshnessStatus.CURRENT,
            quality=EvidenceQuality.VERIFIED,
            missingness=Missingness.PRESENT,
        ),
        Evidence(
            indicator_id="demand",
            raw_value=90,
            unit="synthetic-units",
            geography_id="beta",
            geography_name="Beta",
            geographic_level=GeographicLevel.DISTRICT,
            reference_year=2025,
            dataset_id="beta-demand",
            freshness_status=FreshnessStatus.CURRENT,
            quality=EvidenceQuality.VERIFIED,
            missingness=Missingness.PRESENT,
        ),
        Evidence(
            indicator_id="access",
            raw_value=50,
            unit="synthetic-units",
            geography_id="alpha",
            geography_name="Alpha",
            geographic_level=GeographicLevel.DISTRICT,
            reference_year=2025,
            dataset_id="alpha-access",
            freshness_status=FreshnessStatus.CURRENT,
            quality=EvidenceQuality.VERIFIED,
            missingness=Missingness.PRESENT,
        ),
        Evidence(
            indicator_id="demand",
            raw_value=30,
            unit="synthetic-units",
            geography_id="gamma",
            geography_name="Gamma",
            geographic_level=GeographicLevel.DISTRICT,
            reference_year=2025,
            dataset_id="gamma-demand",
            freshness_status=FreshnessStatus.CURRENT,
            quality=EvidenceQuality.VERIFIED,
            missingness=Missingness.PRESENT,
        ),
    )
    run = build_decision_run(definition, request, alternatives, evidence)
    alpha = next(item for item in run.coverage if item.alternative_id == "alpha")
    beta = next(item for item in run.coverage if item.alternative_id == "beta")
    gamma = next(item for item in run.coverage if item.alternative_id == "gamma")

    assert alpha.required_criteria_satisfied == ("demand", "access")
    assert alpha.optional_criteria_satisfied == ()
    assert alpha.missing_criteria == ()
    assert alpha.effective_weight_represented == pytest.approx(1.0)
    assert alpha.evidence_coverage_percentage == pytest.approx(100.0)

    assert beta.required_criteria_satisfied == ("demand",)
    assert beta.missing_criteria == ("access",)
    assert beta.effective_weight_represented == pytest.approx(0.7)
    assert beta.effective_weight_missing == pytest.approx(0.3)
    assert beta.evidence_coverage_percentage == pytest.approx(70.0)

    assert gamma.required_criteria_satisfied == ("demand",)
    assert gamma.missing_criteria == ("access",)
    assert gamma.effective_weight_represented == pytest.approx(0.7)
    assert gamma.evidence_coverage_percentage == pytest.approx(70.0)


def test_normalization_for_negative_zero_positive_large_and_constant_values() -> None:
    assert min_max_normalize(
        (-10, 0, 10), CriterionDirection.HIGHER_IS_BETTER
    ).values == pytest.approx((0.0, 0.5, 1.0))
    assert min_max_normalize(
        (10, 5, 0), CriterionDirection.LOWER_IS_BETTER
    ).values == pytest.approx((0.0, 0.5, 1.0))
    assert min_max_normalize(
        (0, 0, 0), CriterionDirection.HIGHER_IS_BETTER
    ).values == pytest.approx((1.0, 1.0, 1.0))
    assert min_max_normalize(
        (0, 0), CriterionDirection.HIGHER_IS_BETTER, constant_value=0.0
    ).values == pytest.approx((0.0, 0.0))
    assert min_max_normalize(
        (1e12, 1e12 + 1), CriterionDirection.HIGHER_IS_BETTER
    ).values == pytest.approx((0.0, 1.0))
    normalized = min_max_normalize((-5, -1, 0, 3, 7), CriterionDirection.HIGHER_IS_BETTER).values
    assert all(0.0 <= value <= 1.0 for value in normalized)


def test_weight_traceability_keeps_default_and_override_metadata() -> None:
    definition = make_definition(demand_weight=0.6, access_weight=0.4)
    request = make_request(criterion_weights={"demand": 0.4, "access": 0.6})
    strategy = build_weighting_strategy(definition, request)
    assert strategy.weights[0].default_weight == pytest.approx(0.6)
    assert strategy.weights[0].override_weight == pytest.approx(0.4)
    assert strategy.weights[0].source is WeightSource.USER_OVERRIDE
    assert strategy.weights[1].source is WeightSource.USER_OVERRIDE
    normalized = normalize_weights(strategy)
    assert normalized["demand"] == pytest.approx(0.4)
    assert normalized["access"] == pytest.approx(0.6)

    run = build_decision_run(
        definition,
        request,
        make_alternatives(),
        make_evidence(values={"alpha": (30, 20), "beta": (90, 80), "gamma": (60, 50)}),
    )
    assert run.readiness.state is DecisionReadiness.RECOMMENDATION_READY
    assert run.criterion_scores[0].criterion_scores[0].effective_weight == pytest.approx(0.4)

    with pytest.raises(ValueError):
        build_weighting_strategy(definition, make_request(criterion_weights={"demand": -1.0}))
    with pytest.raises(ValueError):
        normalize_weights(
            build_weighting_strategy(
                definition, make_request(criterion_weights={"demand": 0.0, "access": 0.0})
            )
        )


def test_score_decomposition_invariant_and_component_fields() -> None:
    scores = score_alternatives(
        make_definition(), make_request(), make_alternatives(), make_evidence()
    )
    winner = scores[0]
    assert winner.final_score == pytest.approx(
        sum(component.weighted_contribution for component in winner.criterion_scores)
    )
    for component in winner.criterion_scores:
        assert component.evidence.raw_value is not None
        assert 0.0 <= component.normalized_value <= 1.0
        assert component.default_weight >= 0.0
        assert component.override_weight is None or component.override_weight >= 0.0
        assert component.effective_weight >= 0.0
        assert component.weighted_contribution >= 0.0


def test_true_ties_are_preserved_in_order_and_explanation() -> None:
    definition = make_definition()
    request = make_request()
    tied_alts = (
        DecisionAlternative(identifier="alpha", display_name="Alpha", alternative_type="district"),
        DecisionAlternative(identifier="beta", display_name="Beta", alternative_type="district"),
    )
    evidence = tuple(
        Evidence(
            indicator_id=indicator,
            raw_value=50,
            unit="synthetic-units",
            geography_id=alternative.identifier,
            geography_name=alternative.display_name,
            geographic_level=GeographicLevel.DISTRICT,
            reference_year=2025,
            dataset_id=f"tie-{alternative.identifier}-{indicator}",
            freshness_status=FreshnessStatus.CURRENT,
            quality=EvidenceQuality.VERIFIED,
            missingness=Missingness.PRESENT,
        )
        for alternative in tied_alts
        for indicator in ("demand", "access")
    )
    run = build_decision_run(definition, request, tied_alts, evidence)
    assert run.ties.tied_leader_ids == ("alpha", "beta")
    assert run.ties.display_order == ("alpha", "beta")
    assert run.recommendation is not None
    assert len(run.recommendation.tied_alternatives) == 2
    assert run.explanation is not None
    assert run.explanation.tied_leaders == ("alpha", "beta")
    assert run.recommendation.alternative.identifier in {"alpha", "beta"}


def test_confidence_v1_uses_exact_formula_and_thresholds() -> None:
    evidence = (
        Evidence(
            indicator_id="demand",
            raw_value=10,
            unit="synthetic-units",
            geography_id="alpha",
            geography_name="Alpha",
            geographic_level=GeographicLevel.DISTRICT,
            reference_year=2025,
            dataset_id="dataset-a",
            freshness_status=FreshnessStatus.CURRENT,
            quality=EvidenceQuality.VERIFIED,
            missingness=Missingness.PRESENT,
        ),
        Evidence(
            indicator_id="access",
            raw_value=20,
            unit="synthetic-units",
            geography_id="alpha",
            geography_name="Alpha",
            geographic_level=GeographicLevel.DISTRICT,
            reference_year=2025,
            dataset_id="dataset-b",
            freshness_status=FreshnessStatus.CURRENT,
            quality=EvidenceQuality.VERIFIED,
            missingness=Missingness.PRESENT,
        ),
        Evidence(
            indicator_id="access",
            raw_value=25,
            unit="synthetic-units",
            geography_id="beta",
            geography_name="Beta",
            geographic_level=GeographicLevel.DISTRICT,
            reference_year=2025,
            dataset_id="dataset-c",
            freshness_status=FreshnessStatus.STALE,
            quality=EvidenceQuality.UNKNOWN,
            missingness=Missingness.PRESENT,
        ),
    )
    run = build_decision_run(make_definition(), make_request(), make_alternatives(), evidence)
    confidence = run.confidence
    assert confidence.methodology_version == "confidence-v1"
    assert confidence.evidence_completeness == pytest.approx(1.0)
    assert confidence.freshness == pytest.approx(2 / 3)
    assert confidence.source_quality == pytest.approx(2 / 3)
    assert confidence.score == pytest.approx((1.0 + (2 / 3) + (2 / 3)) / 3)
    assert confidence.band is ConfidenceBand.MEDIUM

    low = ConfidenceAssessment(
        score=0.4, band=ConfidenceBand.LOW, methodology_version="confidence-v1"
    )
    medium = ConfidenceAssessment(
        score=0.5, band=ConfidenceBand.MEDIUM, methodology_version="confidence-v1"
    )
    high = ConfidenceAssessment(
        score=0.8, band=ConfidenceBand.HIGH, methodology_version="confidence-v1"
    )
    assert low.band is ConfidenceBand.LOW
    assert medium.band is ConfidenceBand.MEDIUM
    assert high.band is ConfidenceBand.HIGH


def test_sensitivity_v1_is_deterministic_and_tracks_changes() -> None:
    definition = make_definition(demand_weight=0.5, access_weight=0.5)
    request = make_request()
    alternatives = make_alternatives()

    stable = build_decision_run(definition, request, alternatives, make_evidence())
    assert stable.sensitivity is not None
    assert stable.sensitivity.methodology_version == "local-weight-perturbation-v1"
    assert stable.sensitivity.stable_recommendation is True
    assert stable.sensitivity.cases

    repeated = build_decision_run(definition, request, alternatives, make_evidence())
    assert repeated.sensitivity == stable.sensitivity

    modified = make_evidence(values={"alpha": (80, 10), "beta": (80, 70), "gamma": (85, 10)})
    sensitive = build_decision_run(definition, request, alternatives, modified)
    assert sensitive.sensitivity is not None
    assert sensitive.sensitivity.methodology_version == "local-weight-perturbation-v1"
    assert any(case.leader_changed for case in sensitive.sensitivity.cases)


def test_explanations_and_methodology_metadata_are_structured() -> None:
    run = build_decision_run(
        make_definition(), make_request(), make_alternatives(), make_evidence()
    )
    assert run.explanation is not None
    assert run.explanation.methodology_reference == "weighted_sum-v1"
    assert "highest" in run.explanation.why_winner_ranked_first.lower()
    assert run.explanation.missing_evidence == ()
    assert run.explanation.limitations
    assert run.scoring_methodology_version == "weighted_sum-v1"
    assert run.normalization_methodology_version == "min_max-v1"
    assert run.methodology_version == "decision-v1"
    assert run.confidence.methodology_version == "confidence-v1"
    assert run.sensitivity is not None
    assert run.sensitivity.methodology_version == "local-weight-perturbation-v1"


def test_identical_runs_remain_equal_for_readiness_scores_ranking_and_metadata() -> None:
    definition = make_definition()
    request = make_request()
    alternatives = make_alternatives()
    evidence = make_evidence()

    first = build_decision_run(definition, request, alternatives, evidence)
    second = build_decision_run(definition, request, alternatives, evidence)

    assert first.readiness == second.readiness
    assert first.criterion_scores == second.criterion_scores
    assert first.ranking == second.ranking
    assert first.ties == second.ties
    assert first.confidence == second.confidence
    assert first.sensitivity == second.sensitivity
    assert first.explanation == second.explanation
    assert first.methodology_version == second.methodology_version
    assert first.scoring_methodology_version == second.scoring_methodology_version
    assert first.normalization_methodology_version == second.normalization_methodology_version
