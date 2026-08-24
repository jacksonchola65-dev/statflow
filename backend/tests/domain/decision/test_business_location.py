from __future__ import annotations

from uuid import UUID, uuid4

import pytest
from app.domain.decision import (
    AbstentionReasonCode,
    BusinessLocationMode,
    BusinessLocationRequest,
    CriterionDirection,
    DecisionAlternative,
    Evidence,
    EvidenceQuality,
    FreshnessStatus,
    GeographicLevel,
    Missingness,
    build_business_location_definition,
    build_business_location_run,
    get_business_category_profile,
)
from app.services.business_location_service import resolve_district_candidates


def _request(**kwargs) -> BusinessLocationRequest:
    payload = {
        "business_category": "supermarket",
        "province_code": "TP",
        "original_question": "Which district presents the strongest opportunity?",
        "reference_year": 2025,
    }
    payload.update(kwargs)
    return BusinessLocationRequest(**payload)


def _alternatives() -> tuple[DecisionAlternative, ...]:
    return tuple(
        DecisionAlternative(
            identifier=identifier,
            display_name=name,
            alternative_type="district",
            metadata={"province_code": "TP"},
        )
        for identifier, name in (("alpha", "Alpha"), ("beta", "Beta"), ("gamma", "Gamma"))
    )


def _evidence(values: dict[str, dict[str, float | None]]) -> tuple[Evidence, ...]:
    return tuple(
        Evidence(
            indicator_id=criterion,
            raw_value=value,
            unit="synthetic-units",
            geography_id=alternative,
            geography_name=alternative.title(),
            geographic_level=GeographicLevel.DISTRICT,
            reference_year=2025,
            dataset_id="business-location-test-fixture",
            dataset_version="1",
            source_institution="Synthetic Test Source",
            source_reference="synthetic://business-location",
            quality=EvidenceQuality.VERIFIED,
            freshness_status=FreshnessStatus.CURRENT,
            missingness=Missingness.PRESENT if value is not None else Missingness.MISSING,
        )
        for alternative, criteria in values.items()
        for criterion, value in criteria.items()
    )


FULL_VALUES = {
    "alpha": {
        "market_demand": 60,
        "market_growth": 50,
        "purchasing_power": 40,
        "accessibility": 70,
        "competition": 30,
        "operating_feasibility": 60,
    },
    "beta": {
        "market_demand": 80,
        "market_growth": 70,
        "purchasing_power": 75,
        "accessibility": 90,
        "competition": 20,
        "operating_feasibility": 80,
    },
    "gamma": {
        "market_demand": 40,
        "market_growth": 30,
        "purchasing_power": 35,
        "accessibility": 50,
        "competition": 60,
        "operating_feasibility": 40,
    },
}


def test_model_identity_profiles_weights_and_criteria_are_explicit() -> None:
    profile = get_business_category_profile("supermarket")
    definition = build_business_location_definition(profile)

    assert definition.identifier == "BUSINESS_LOCATION_OPPORTUNITY"
    assert definition.version == "business-location-v1"
    assert definition.geographic_level is GeographicLevel.DISTRICT
    assert sum(profile.criterion_weights.values()) == pytest.approx(1.0)
    assert {criterion.identifier for criterion in definition.criteria} == {
        "market_demand",
        "market_growth",
        "purchasing_power",
        "accessibility",
        "competition",
        "operating_feasibility",
    }
    assert definition.criteria[4].direction is CriterionDirection.LOWER_IS_BETTER
    assert get_business_category_profile("general-retail").category_id == "GENERAL_RETAIL"


def test_candidate_resolution_is_exact_and_deterministic() -> None:
    province_id = uuid4()
    other_province_id = uuid4()
    province = type("ProvinceFixture", (), {"id": province_id, "code": "TP"})()
    districts = [
        type(
            "DistrictFixture",
            (),
            {"id": UUID(int=3), "name": "Gamma", "code": "TP-G", "province_id": province_id},
        )(),
        type(
            "DistrictFixture",
            (),
            {"id": UUID(int=2), "name": "Beta", "code": "TP-B", "province_id": province_id},
        )(),
        type(
            "DistrictFixture",
            (),
            {"id": UUID(int=1), "name": "Alpha", "code": "TP-A", "province_id": other_province_id},
        )(),
    ]

    resolved = resolve_district_candidates(province, districts)

    assert [item.display_name for item in resolved.candidates] == ["Beta", "Gamma"]
    assert len(resolved.excluded) == 1
    assert resolved.excluded[0].eligibility.value == "excluded"
    assert resolved.excluded[0].exclusion_reasons == ("district is outside the requested province",)


def test_full_controlled_fixture_produces_complete_explainable_run() -> None:
    result = build_business_location_run(_request(), _alternatives(), _evidence(FULL_VALUES))
    decision = result.decision

    assert result.criteria_unavailable == ()
    assert decision.readiness.state.value == "recommendation_ready"
    assert decision.ranking == ("beta", "alpha", "gamma")
    assert decision.recommendation is not None
    assert decision.recommendation.alternative.identifier == "beta"
    assert decision.methodology_version == "business-location-v1"
    assert decision.explanation is not None
    assert decision.explanation.methodology_reference == "business-location-v1"
    assert decision.sensitivity is not None
    assert decision.confidence.evidence_completeness == pytest.approx(1.0)
    assert decision.criterion_scores[0].criterion_scores
    assert all(
        item.evidence.source_reference == "synthetic://business-location"
        for item in decision.criterion_scores[0].criterion_scores
    )


def test_production_like_missing_evidence_abstains_without_fabricated_components() -> None:
    values = {
        alternative: {"market_demand": criteria["market_demand"]}
        for alternative, criteria in FULL_VALUES.items()
    }
    result = build_business_location_run(_request(), _alternatives(), _evidence(values))
    decision = result.decision

    assert result.criteria_used == ("market_demand",)
    assert set(result.criteria_unavailable) == {
        "market_growth",
        "purchasing_power",
        "accessibility",
        "competition",
        "operating_feasibility",
    }
    assert decision.readiness.state.value == "insufficient_evidence"
    assert decision.recommendation is None
    assert decision.criterion_scores == ()
    assert AbstentionReasonCode.INSUFFICIENT_CRITERION_COVERAGE in decision.readiness.reasons
    assert decision.explanation is not None
    assert decision.explanation.missing_evidence == ("alpha", "beta", "gamma")


def test_exploratory_mode_is_explicit_and_still_surfaces_missing_criteria() -> None:
    values = {
        alternative: {"market_demand": criteria["market_demand"]}
        for alternative, criteria in FULL_VALUES.items()
    }
    result = build_business_location_run(
        _request(mode=BusinessLocationMode.EXPLORATORY), _alternatives(), _evidence(values)
    )

    assert result.mode is BusinessLocationMode.EXPLORATORY
    assert result.decision.readiness.state.value == "recommendation_ready"
    assert result.decision.explanation is not None
    assert "not a production-grade recommendation" in " ".join(
        result.decision.explanation.limitations
    )


def test_user_overrides_ties_and_repeated_runs_are_deterministic() -> None:
    request = _request(criterion_weights={"accessibility": 0.9, "market_demand": 0.1})
    first = build_business_location_run(request, _alternatives(), _evidence(FULL_VALUES))
    second = build_business_location_run(request, _alternatives(), _evidence(FULL_VALUES))

    assert first == second
    assert first.decision.criterion_scores[0].criterion_scores[0].override_weight is not None
    assert first.decision.ties.display_order == first.decision.ranking
