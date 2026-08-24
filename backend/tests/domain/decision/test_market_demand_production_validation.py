from __future__ import annotations

import pytest
from app.domain.decision import (
    BusinessLocationRequest,
    CriterionDirection,
    DecisionAlternative,
    DecisionCriterion,
    DecisionDefinition,
    DecisionRequest,
    Evidence,
    EvidenceQuality,
    FreshnessStatus,
    GeographicLevel,
    IndicatorRequirement,
    build_business_location_run,
    build_decision_run,
)

POPULATIONS = {
    "LP-CHEMBE": 51634,
    "LP-CHIENGE": 190566,
    "LP-CHIFUNABULI": 116634,
    "LP-CHIPILI": 47473,
    "LP-KAWAMBWA": 124046,
    "LP-LUNGA": 39462,
    "LP-MANSA": 329622,
    "LP-MILENGE": 56638,
    "LP-MWANSABOMBWE": 58992,
    "LP-MWENSE": 122796,
    "LP-NCHELENGE": 234259,
    "LP-SAMFYA": 147356,
}


def _controlled_inputs() -> tuple[
    DecisionDefinition, DecisionRequest, tuple[DecisionAlternative, ...], tuple[Evidence, ...]
]:
    definition = DecisionDefinition(
        identifier="MARKET_DEMAND_CONTROLLED",
        name="Market Demand Only",
        description="Production validation fixture",
        version="market-demand-validation-v1",
        geographic_level=GeographicLevel.DISTRICT,
        criteria=(
            DecisionCriterion(
                identifier="market_demand",
                name="Market Demand",
                direction=CriterionDirection.HIGHER_IS_BETTER,
                weight=1.0,
                indicator_requirements=(
                    IndicatorRequirement(
                        indicator_id="market_demand",
                        name="Market Demand",
                        geographic_level=GeographicLevel.DISTRICT,
                    ),
                ),
            ),
        ),
    )
    request = DecisionRequest(
        decision_definition_id=definition.identifier,
        original_question="Which district has the highest market demand?",
        geographic_scope="LP",
        reference_year=2022,
    )
    alternatives = tuple(
        DecisionAlternative(
            identifier=code,
            display_name=code.removeprefix("LP-"),
            alternative_type="district",
            metadata={"district_code": code},
        )
        for code in POPULATIONS
    )
    evidence = tuple(
        Evidence(
            indicator_id="market_demand",
            indicator_name="Total Population",
            raw_value=value,
            unit="People",
            geography_id=code,
            geography_name=code.removeprefix("LP-"),
            geographic_level=GeographicLevel.DISTRICT,
            reference_year=2022,
            dataset_id="2022-census-luapula",
            dataset_name="2022 Census of Population and Housing - Luapula District",
            source_institution="Zambia Statistics Agency (ZamStats)",
            source_reference="https://www.zamstats.gov.zm/2022-census-of-population-and-housing-summary-report-part-2/",
            quality=EvidenceQuality.UNKNOWN,
            freshness_status=FreshnessStatus.CURRENT,
        )
        for code, value in POPULATIONS.items()
    )
    return definition, request, alternatives, evidence


def test_authoritative_values_normalize_and_rank_deterministically() -> None:
    definition, request, alternatives, evidence = _controlled_inputs()
    first = build_decision_run(definition, request, alternatives, evidence)
    second = build_decision_run(definition, request, alternatives, evidence)

    scores = {item.alternative.identifier: item for item in first.criterion_scores}
    assert first == second
    assert first.ranking[0] == "LP-MANSA"
    assert first.ranking[-1] == "LP-LUNGA"
    assert scores["LP-LUNGA"].criterion_scores[0].normalized_value == pytest.approx(0.0)
    assert scores["LP-MANSA"].criterion_scores[0].normalized_value == pytest.approx(1.0)
    for code, value in POPULATIONS.items():
        expected = (value - 39462) / (329622 - 39462)
        component = scores[code].criterion_scores[0]
        assert component.normalized_value == pytest.approx(expected)
        assert component.effective_weight == pytest.approx(1.0)
        assert component.weighted_contribution == pytest.approx(component.normalized_value)
        assert scores[code].final_score == pytest.approx(component.weighted_contribution)
        assert component.evidence.source_institution == "Zambia Statistics Agency (ZamStats)"
        assert component.evidence.reference_year == 2022


def test_explanation_derives_leader_from_score_components() -> None:
    definition, request, alternatives, evidence = _controlled_inputs()
    run = build_decision_run(definition, request, alternatives, evidence)
    explanation = run.explanation

    assert explanation is not None
    assert "highest" in explanation.why_winner_ranked_first.lower()
    assert "raw=329622" in explanation.why_winner_ranked_first
    assert "normalized=1.000000" in explanation.why_winner_ranked_first
    assert "effective_weight=1.000000" in explanation.why_winner_ranked_first
    assert "contribution=1.000000" in explanation.why_winner_ranked_first


def test_single_criterion_sensitivity_is_stable() -> None:
    definition, request, alternatives, evidence = _controlled_inputs()
    run = build_decision_run(definition, request, alternatives, evidence)

    assert run.sensitivity is not None
    assert run.sensitivity.stable_recommendation is True
    assert run.sensitivity.sensitive_criteria == ()
    assert {case.leader_id for case in run.sensitivity.cases} == {"LP-MANSA"}


def test_business_location_does_not_promote_market_demand_leader() -> None:
    _, _, alternatives, evidence = _controlled_inputs()
    request = BusinessLocationRequest(
        business_category="supermarket",
        province_code="LP",
        original_question="Where should the business locate?",
        reference_year=2022,
    )
    result = build_business_location_run(request, alternatives, evidence)

    assert result.criteria_used == ("market_demand",)
    assert set(result.criteria_unavailable) == {
        "market_growth",
        "purchasing_power",
        "accessibility",
        "competition",
        "operating_feasibility",
    }
    assert result.decision.readiness.state.value == "insufficient_evidence"
    assert result.decision.recommendation is None
    assert result.decision.ranking == ()
