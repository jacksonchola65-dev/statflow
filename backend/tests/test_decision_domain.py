from __future__ import annotations

from datetime import date

import pytest
from app.domain.decision import (
    CriterionDirection,
    DecisionAlternative,
    DecisionCriterion,
    DecisionDefinition,
    DecisionDomainError,
    DecisionRequest,
    EligibilityState,
    Evidence,
    EvidenceQuality,
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
from pydantic import ValidationError


def test_normalization_higher_lower_zero_and_constant_series() -> None:
    assert min_max_normalize((0, 5, 10), CriterionDirection.HIGHER_IS_BETTER).values == (
        0.0,
        0.5,
        1.0,
    )
    assert min_max_normalize((0, 5, 10), CriterionDirection.LOWER_IS_BETTER).values == (
        1.0,
        0.5,
        0.0,
    )
    assert min_max_normalize((0, 0, 0), CriterionDirection.HIGHER_IS_BETTER).values == (
        1.0,
        1.0,
        1.0,
    )
    assert min_max_normalize(
        (0, 0), CriterionDirection.HIGHER_IS_BETTER, constant_value=0.0
    ).values == (
        0.0,
        0.0,
    )


def test_missing_values_are_rejected_not_converted_to_zero() -> None:
    with pytest.raises(DecisionDomainError, match="non-missing"):
        min_max_normalize((0, None, 10), CriterionDirection.HIGHER_IS_BETTER)


def test_evidence_missingness_contract_is_explicit() -> None:
    evidence = Evidence(
        indicator_id="demand",
        raw_value=None,
        geography_id="alpha",
        geography_name="Alpha",
        dataset_id="synthetic-location-fixture",
        missingness=Missingness.MISSING,
    )
    assert evidence.missingness is Missingness.MISSING
    with pytest.raises((DecisionDomainError, ValidationError)):
        Evidence(
            indicator_id="demand",
            raw_value=1,
            geography_id="alpha",
            geography_name="Alpha",
            dataset_id="synthetic-location-fixture",
            missingness=Missingness.MISSING,
        )


def test_weight_validation_and_override_provenance() -> None:
    definition = fixture_definition()
    request = fixture_request(criterion_weights={"demand": 3.0, "access": 1.0})
    strategy = build_weighting_strategy(definition, request)
    normalized = normalize_weights(strategy)
    assert normalized == {"demand": 0.75, "access": 0.25}
    assert strategy.weights[0].source is WeightSource.USER_OVERRIDE
    with pytest.raises(ValidationError, match="greater than or equal to 0"):
        build_weighting_strategy(definition, fixture_request(criterion_weights={"demand": -1.0}))
    with pytest.raises(DecisionDomainError, match="unknown"):
        build_weighting_strategy(definition, fixture_request(criterion_weights={"unknown": 1.0}))


def test_synthetic_fixture_proves_winner_mathematically() -> None:
    definition = fixture_definition()
    request = fixture_request()
    alternatives = fixture_alternatives()
    evidence = fixture_evidence()
    scores = score_alternatives(definition, request, alternatives, evidence)
    assert [score.alternative.identifier for score in scores] == ["beta", "alpha", "gamma"]
    assert scores[0].final_score == pytest.approx(1.0)
    assert [
        component.weighted_contribution for component in scores[0].criterion_scores
    ] == pytest.approx([0.5, 0.5])
    assert sum(
        component.weighted_contribution for component in scores[0].criterion_scores
    ) == pytest.approx(scores[0].final_score)
    assert scores[0].criterion_scores[0].evidence.raw_value == 80


def test_ranking_is_deterministic_and_ties_use_identifier() -> None:
    definition = fixture_definition()
    request = fixture_request()
    alternatives = fixture_alternatives()
    evidence = fixture_evidence()
    first = score_alternatives(definition, request, alternatives, evidence)
    second = score_alternatives(definition, request, alternatives, evidence)
    assert first == second

    tied = (
        DecisionAlternative(identifier="zeta", display_name="Zeta", alternative_type="district"),
        DecisionAlternative(identifier="alpha", display_name="Alpha", alternative_type="district"),
    )
    tied_evidence = tuple(
        Evidence(
            indicator_id=indicator,
            raw_value=50,
            geography_id=alternative.identifier,
            geography_name=alternative.display_name,
            dataset_id="synthetic-location-fixture",
        )
        for alternative in tied
        for indicator in ("demand", "access")
    )
    assert [
        score.alternative.identifier
        for score in score_alternatives(definition, request, tied, tied_evidence)
    ] == [
        "alpha",
        "zeta",
    ]


def test_excluded_alternative_is_not_scored() -> None:
    alternatives = fixture_alternatives()[:-1] + (
        DecisionAlternative(
            identifier="gamma",
            display_name="Gamma",
            alternative_type="district",
            eligibility=EligibilityState.EXCLUDED,
            exclusion_reasons=("outside requested scope",),
        ),
    )
    scores = score_alternatives(
        fixture_definition(), fixture_request(), alternatives, fixture_evidence()
    )
    assert [score.alternative.identifier for score in scores] == ["beta", "alpha"]


def test_required_missing_evidence_fails_and_optional_missing_is_renormalized() -> None:
    definition = fixture_definition(required_access=False)
    evidence = tuple(
        item
        for item in fixture_evidence()
        if not (item.geography_id == "gamma" and item.indicator_id == "access")
    )
    scores = score_alternatives(definition, fixture_request(), fixture_alternatives(), evidence)
    gamma = next(score for score in scores if score.alternative.identifier == "gamma")
    assert len(gamma.criterion_scores) == 1
    assert gamma.criterion_scores[0].effective_weight == pytest.approx(1.0)

    with pytest.raises(DecisionDomainError, match="required evidence missing"):
        score_alternatives(
            fixture_definition(), fixture_request(), fixture_alternatives(), evidence
        )


def test_decision_run_retains_request_model_version_evidence_and_recommendation() -> None:
    definition = fixture_definition()
    request = fixture_request()
    confidence = {"level": "initial"}
    run = build_decision_run(
        definition,
        request,
        fixture_alternatives(),
        fixture_evidence(),
        confidence=confidence,
    )
    assert run.request == request
    assert run.definition.version == "location-opportunity-1"
    assert run.evidence_used == fixture_evidence()
    assert run.ranking == ("beta", "alpha", "gamma")
    assert run.recommendation is not None


def fixture_definition(*, required_access: bool = True) -> DecisionDefinition:
    return DecisionDefinition(
        identifier="business-location-opportunity",
        name="Business Location Opportunity Analysis",
        description="Synthetic test model only; not a production recommendation.",
        version="location-opportunity-1",
        geographic_level=GeographicLevel.DISTRICT,
        criteria=(
            DecisionCriterion(
                identifier="demand",
                name="Synthetic demand",
                direction=CriterionDirection.HIGHER_IS_BETTER,
                weight=0.5,
                indicator_requirements=(
                    IndicatorRequirement(indicator_id="demand", name="Synthetic demand"),
                ),
            ),
            DecisionCriterion(
                identifier="access",
                name="Synthetic accessibility",
                direction=CriterionDirection.HIGHER_IS_BETTER,
                weight=0.5,
                required=required_access,
                indicator_requirements=(
                    IndicatorRequirement(indicator_id="access", name="Synthetic access"),
                ),
            ),
        ),
    )


def fixture_request(*, criterion_weights: dict[str, float] | None = None) -> DecisionRequest:
    return DecisionRequest(
        decision_definition_id="business-location-opportunity",
        original_question="Synthetic test: where should the business open?",
        business_category="synthetic-business",
        geographic_scope="synthetic-province",
        criterion_weights=criterion_weights or {},
    )


def fixture_alternatives() -> tuple[DecisionAlternative, ...]:
    return tuple(
        DecisionAlternative(identifier=name.lower(), display_name=name, alternative_type="district")
        for name in ("Alpha", "Beta", "Gamma")
    )


def fixture_evidence() -> tuple[Evidence, ...]:
    values = {"alpha": (60, 40), "beta": (80, 70), "gamma": (40, 10)}
    return tuple(
        Evidence(
            indicator_id=indicator,
            raw_value=value,
            unit="synthetic-units",
            geography_id=alternative,
            geography_name=alternative.title(),
            reference_year=2025,
            dataset_id="synthetic-location-fixture",
            dataset_version="1",
            source_institution="Synthetic Test Source",
            source_reference="synthetic://fixture/location-opportunity",
            freshness_date=date(2025, 12, 31),
            quality=EvidenceQuality.VERIFIED,
        )
        for alternative, values in values.items()
        for indicator, value in zip(("demand", "access"), values)
    )
