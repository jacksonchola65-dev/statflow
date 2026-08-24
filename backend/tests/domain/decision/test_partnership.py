from __future__ import annotations

import pytest
from app.domain.decision import get_business_category_profile
from app.domain.decision.partnership import (
    build_partnership_requirements,
    partnership_requirements_for_partner,
    readiness_scenario,
)


def test_all_blocked_criteria_have_deterministic_partnership_requirements() -> None:
    requirements = build_partnership_requirements(get_business_category_profile("SUPERMARKET"))

    assert [item.criterion_id for item in requirements] == [
        "accessibility",
        "purchasing_power",
        "competition",
        "market_growth",
        "operating_feasibility",
    ]
    assert all(
        item.current_availability_state.value == "blocked_by_evidence" for item in requirements
    )
    assert all(item.required_geography.value == "district" for item in requirements)
    assert all(item.contact_status.startswith("candidate partner") for item in requirements)


def test_partner_views_are_filtered_without_claiming_data_availability() -> None:
    profile = get_business_category_profile("SUPERMARKET")

    zamstats = partnership_requirements_for_partner(profile, "ZamStats")
    assert [item.criterion_id for item in zamstats] == [
        "purchasing_power",
        "competition",
        "market_growth",
    ]
    assert all("candidate partner" in item.contact_status for item in zamstats)

    pacra = partnership_requirements_for_partner(profile, "PACRA")
    assert [item.criterion_id for item in pacra] == ["competition"]
    assert any("registration" in limitation for limitation in pacra[0].limitations)

    zicta = partnership_requirements_for_partner(profile, "ZICTA")
    assert [item.criterion_id for item in zicta] == ["accessibility", "operating_feasibility"]


def test_readiness_scenario_changes_only_readiness() -> None:
    scenario = readiness_scenario(get_business_category_profile("SUPERMARKET"), "competition")

    assert scenario.current_readiness_percentage == pytest.approx(25.0)
    assert scenario.projected_readiness_percentage == pytest.approx(40.0)
    assert scenario.recommendation_allowed is False
    assert "does not fabricate evidence" in scenario.note


def test_unknown_or_ready_criteria_cannot_have_hypothetical_scenario() -> None:
    with pytest.raises(ValueError):
        readiness_scenario(get_business_category_profile("SUPERMARKET"), "unknown")
    with pytest.raises(ValueError):
        readiness_scenario(get_business_category_profile("SUPERMARKET"), "market_demand")
