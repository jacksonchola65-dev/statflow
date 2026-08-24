from __future__ import annotations

from pathlib import Path
from uuid import UUID

import pytest
import pytest_asyncio
from app.domain.decision import (
    BusinessLocationRequest,
    CriterionDirection,
    DecisionAlternative,
    DecisionCriterion,
    DecisionDefinition,
    DecisionRequest,
    EvidenceQuality,
    GeographicLevel,
    IndicatorRequirement,
    build_business_location_run,
    build_decision_run,
    build_weighting_strategy,
    min_max_normalize,
    normalize_weights,
)
from app.domain.decision.resolver import EvidenceResolutionStatus
from app.models.category import Category
from app.models.district import District
from app.models.indicator import Indicator
from app.models.province import Province
from app.services.decision_evidence import DecisionEvidenceResolver
from app.services.district_population_ingestion_service import (
    DistrictPopulationIngestionService,
    IngestionStatus,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

EXPECTED_POPULATIONS = {
    "Chembe": 51634,
    "Chienge": 190566,
    "Chifunabuli": 116634,
    "Chipili": 47473,
    "Kawambwa": 124046,
    "Lunga": 39462,
    "Mansa": 329622,
    "Milenge": 56638,
    "Mwansabombwe": 58992,
    "Mwense": 122796,
    "Nchelenge": 234259,
    "Samfya": 147356,
}


@pytest_asyncio.fixture
async def market_demand_records(db_session: AsyncSession):
    province = (
        await db_session.execute(select(Province).where(Province.code == "LP"))
    ).scalar_one()
    for name in EXPECTED_POPULATIONS:
        district = (
            await db_session.execute(select(District).where(District.name == name))
        ).scalar_one_or_none()
        if district is None:
            db_session.add(
                District(
                    province_id=province.id,
                    code=f"LP-{name.upper().replace(' ', '')}",
                    name=name,
                )
            )
    category = (await db_session.execute(select(Category).limit(1))).scalar_one()
    indicator = (
        await db_session.execute(select(Indicator).where(Indicator.code == "POP_TOTAL"))
    ).scalar_one_or_none()
    if indicator is None:
        indicator = Indicator(
            category_id=category.id,
            code="POP_TOTAL",
            name="Total Population",
            description="Total population count",
            unit="People",
        )
        db_session.add(indicator)
    await db_session.flush()
    csv_path = (
        Path(__file__).parents[2]
        / "docs"
        / "evidence"
        / "luapula_district_population_2022_verified.csv"
    )
    result = await DistrictPopulationIngestionService(db_session).ingest_csv(csv_path)
    assert result.status is IngestionStatus.SUCCESS
    assert result.created_datapoints == 12
    return province, indicator


def _market_definition(indicator_id: str) -> DecisionDefinition:
    return DecisionDefinition(
        identifier="market-demand-only-validation",
        name="Market-Demand-Only Validation",
        description="Controlled validation scenario; not a production recommendation.",
        version="market-demand-validation-v1",
        geographic_level=GeographicLevel.DISTRICT,
        criteria=(
            DecisionCriterion(
                identifier="market_demand",
                name="Market demand",
                direction=CriterionDirection.HIGHER_IS_BETTER,
                weight=1.0,
                indicator_requirements=(
                    IndicatorRequirement(
                        indicator_id=indicator_id,
                        name="Total Population",
                        geographic_level=GeographicLevel.DISTRICT,
                    ),
                ),
            ),
        ),
    )


@pytest.mark.asyncio
async def test_market_demand_production_validation(db_session, market_demand_records):
    province, indicator = market_demand_records
    districts = list(
        (
            await db_session.execute(
                select(District).where(District.province_id == province.id).order_by(District.name)
            )
        ).scalars()
    )
    alternatives = tuple(
        DecisionAlternative(
            identifier=str(district.id), display_name=district.name, alternative_type="district"
        )
        for district in districts
    )
    definition = _market_definition(str(indicator.id))
    request = DecisionRequest(
        decision_definition_id=definition.identifier,
        original_question="Controlled Market-Demand-only ranking",
        geographic_scope="LP",
        reference_year=2022,
    )
    requirement = definition.criteria[0].indicator_requirements[0]
    resolver = DecisionEvidenceResolver(db_session)
    resolutions = tuple(
        [await resolver.resolve(requirement, alternative, request) for alternative in alternatives]
    )

    assert all(item.status is EvidenceResolutionStatus.RESOLVED for item in resolutions)
    assert len(resolutions) == 12
    evidence = tuple(item.evidence for item in resolutions if item.evidence is not None)
    assert {item.geography_name: int(item.raw_value) for item in evidence} == EXPECTED_POPULATIONS
    assert all(item.reference_year == 2022 for item in evidence)
    assert all(
        item.source_institution == "Zambia Statistics Agency (ZamStats)" for item in evidence
    )
    assert all(item.freshness_status.value == "current" for item in evidence)
    assert all(item.quality is EvidenceQuality.UNKNOWN for item in evidence)

    values = tuple(item.raw_value for item in evidence)
    normalized = min_max_normalize(values, CriterionDirection.HIGHER_IS_BETTER).values
    expected = {
        item.geography_name: (float(item.raw_value) - 39462.0) / (329622.0 - 39462.0)
        for item in evidence
    }
    assert normalized[tuple(item.geography_name for item in evidence).index("Lunga")] == 0.0
    assert normalized[tuple(item.geography_name for item in evidence).index("Mansa")] == 1.0
    assert normalized == pytest.approx(tuple(expected[item.geography_name] for item in evidence))

    strategy = build_weighting_strategy(definition, request)
    assert normalize_weights(strategy) == {"market_demand": 1.0}
    first = build_decision_run(definition, request, alternatives, evidence)
    second = build_decision_run(definition, request, alternatives, evidence)
    assert first == second
    assert first.ranking == tuple(
        str(item.alternative.identifier)
        for item in sorted(
            first.criterion_scores,
            key=lambda score: -score.criterion_scores[0].evidence.raw_value,
        )
    )
    assert first.recommendation is not None
    assert first.recommendation.alternative.display_name == "Mansa"
    assert first.confidence.evidence_completeness == pytest.approx(1.0)
    assert first.confidence.freshness == pytest.approx(1.0)
    assert first.confidence.source_quality == pytest.approx(0.0)
    assert first.confidence.score == pytest.approx(2 / 3)
    assert "evidence readiness" in first.confidence.limitations[0]
    assert first.sensitivity is not None
    assert first.sensitivity.stable_recommendation is True
    assert all(case.leader_id == first.ranking[0] for case in first.sensitivity.cases)
    for score in first.criterion_scores:
        component = score.criterion_scores[0]
        assert component.effective_weight == pytest.approx(1.0)
        assert component.weighted_contribution == pytest.approx(component.normalized_value)
        assert score.final_score == pytest.approx(component.weighted_contribution)
        assert (
            component.evidence.dataset_name
            == "2022 Census of Population and Housing - Luapula District"
        )
        assert UUID(component.evidence.dataset_id)
    assert "Mansa" in first.explanation.why_winner_ranked_first
    assert "normalized=1.000000" in first.explanation.why_winner_ranked_first

    production_evidence = tuple(
        item.model_copy(update={"indicator_id": "market_demand"}) for item in evidence
    )
    business = build_business_location_run(
        BusinessLocationRequest(
            business_category="supermarket",
            province_code="LP",
            original_question="Where should a business locate?",
            reference_year=2022,
        ),
        alternatives,
        production_evidence,
    )
    assert business.criteria_used == ("market_demand",)
    assert set(business.criteria_unavailable) == {
        "market_growth",
        "purchasing_power",
        "accessibility",
        "competition",
        "operating_feasibility",
    }
    assert business.decision.readiness.state.value == "insufficient_evidence"
    assert business.decision.recommendation is None
    assert "Mansa" not in business.decision.explanation.why_winner_ranked_first
