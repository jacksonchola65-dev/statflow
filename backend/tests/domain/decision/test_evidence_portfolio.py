from __future__ import annotations

import pytest
from app.domain.decision import (
    BusinessLocationEvidencePortfolio,
    CriterionReadinessState,
    ReadinessBlocker,
    build_business_location_evidence_portfolio,
    build_business_location_run,
    get_business_category_profile,
)

from tests.domain.decision.test_business_location import _alternatives, _evidence, _request


def test_current_portfolio_has_explicit_states_and_weighted_readiness() -> None:
    portfolio = build_business_location_evidence_portfolio(
        get_business_category_profile("supermarket")
    )

    assert isinstance(portfolio, BusinessLocationEvidencePortfolio)
    assert [item.state for item in portfolio.criteria] == [
        CriterionReadinessState.PRODUCTION_USABLE,
        CriterionReadinessState.BLOCKED_BY_EVIDENCE,
        CriterionReadinessState.BLOCKED_BY_EVIDENCE,
        CriterionReadinessState.BLOCKED_BY_EVIDENCE,
        CriterionReadinessState.BLOCKED_BY_EVIDENCE,
        CriterionReadinessState.BLOCKED_BY_EVIDENCE,
    ]
    assert portfolio.readiness_percentage == pytest.approx(25.0)
    assert portfolio.blocking_criteria == (
        "market_growth",
        "purchasing_power",
        "accessibility",
        "competition",
        "operating_feasibility",
    )
    assert ReadinessBlocker.BOUNDARY_INCOMPATIBILITY in portfolio.criteria[1].blockers
    assert portfolio.criteria[4].partner_map == (
        "PACRA",
        "Local councils",
        "Zambia Statistics Agency / ZamStats",
    )
    assert portfolio.blocking_reasons == tuple(
        (item.criterion_id, item.blockers) for item in portfolio.criteria[1:]
    )


def test_portfolio_recalculates_deterministically_when_criteria_unblock() -> None:
    profile = get_business_category_profile("supermarket")
    policy = {
        item.criterion_id: {
            "state": item.state,
            "coverage": item.evidence_coverage_percentage,
            "freshness": item.freshness_status,
            "authority": item.source_authority,
            "blockers": item.blockers,
            "future": item.required_future_evidence,
            "limitations": item.limitations,
            "partner": item.partner_map,
        }
        for item in build_business_location_evidence_portfolio(profile).criteria
    }
    policy["market_growth"]["state"] = CriterionReadinessState.PRODUCTION_USABLE
    first = build_business_location_evidence_portfolio(profile, readiness_policy=policy)
    second = build_business_location_evidence_portfolio(profile, readiness_policy=policy)

    assert first == second
    assert first.readiness_percentage == pytest.approx(40.0)
    assert first.blocking_criteria == (
        "purchasing_power",
        "accessibility",
        "competition",
        "operating_feasibility",
    )


def test_production_gate_abstains_while_exploratory_mode_is_explicit() -> None:
    values = {
        alternative: {"market_demand": criteria["market_demand"]}
        for alternative, criteria in {
            "alpha": {"market_demand": 60},
            "beta": {"market_demand": 80},
            "gamma": {"market_demand": 40},
        }.items()
    }
    production = build_business_location_run(_request(), _alternatives(), _evidence(values))
    exploratory = build_business_location_run(
        _request(mode="exploratory"), _alternatives(), _evidence(values)
    )

    assert production.decision.recommendation is None
    assert production.decision.readiness.state.value == "insufficient_evidence"
    assert exploratory.decision.recommendation is not None
    assert "not a production-grade recommendation" in " ".join(
        exploratory.decision.explanation.limitations
    )
