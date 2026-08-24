from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import pytest
import pytest_asyncio
from app.domain.decision import (
    AbstentionReasonCode,
    BusinessLocationMode,
    BusinessLocationRequest,
    CriterionDirection,
    DecisionAlternative,
    DecisionCriterion,
    DecisionDefinition,
    DecisionRequest,
    EvidenceQuality,
    FreshnessStatus,
    GeographicLevel,
    IndicatorRequirement,
    build_business_location_evidence_portfolio,
    build_business_location_run,
    build_decision_run,
    get_business_category_profile,
    min_max_normalize,
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

EXPECTED_CODES = (
    "LP-CHEMBE",
    "LP-CHIENGE",
    "LP-CHIFUNABULI",
    "LP-CHIPILI",
    "LP-KAWAMBWA",
    "LP-LUNGA",
    "LP-MANSA",
    "LP-MILENGE",
    "LP-MWANSABOMBWE",
    "LP-MWENSE",
    "LP-NCHELENGE",
    "LP-SAMFYA",
)
DISTRICT_NAMES_BY_CODE = {
    "LP-CHEMBE": "Chembe",
    "LP-CHIENGE": "Chienge",
    "LP-CHIFUNABULI": "Chifunabuli",
    "LP-CHIPILI": "Chipili",
    "LP-KAWAMBWA": "Kawambwa",
    "LP-LUNGA": "Lunga",
    "LP-MANSA": "Mansa",
    "LP-MILENGE": "Milenge",
    "LP-MWANSABOMBWE": "Mwansabombwe",
    "LP-MWENSE": "Mwense",
    "LP-NCHELENGE": "Nchelenge",
    "LP-SAMFYA": "Samfya",
}
EXPECTED_RANKING = (
    "Mansa",
    "Nchelenge",
    "Chienge",
    "Samfya",
    "Kawambwa",
    "Mwense",
    "Chifunabuli",
    "Mwansabombwe",
    "Milenge",
    "Chembe",
    "Chipili",
    "Lunga",
)


@pytest_asyncio.fixture
async def real_luapula(db_session: AsyncSession):
    province = (
        await db_session.execute(select(Province).where(Province.code == "LP"))
    ).scalar_one()
    for code, name in DISTRICT_NAMES_BY_CODE.items():
        district = (
            await db_session.execute(select(District).where(District.code == code))
        ).scalar_one_or_none()
        if district is None:
            db_session.add(District(province_id=province.id, code=code, name=name))
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
    imported = await DistrictPopulationIngestionService(db_session).ingest_csv(csv_path)
    assert imported.status is IngestionStatus.SUCCESS, imported.validation_errors
    districts = list(
        (
            await db_session.execute(
                select(District)
                .where(District.province_id == province.id)
                .where(District.code.in_(EXPECTED_CODES))
                .order_by(District.code)
            )
        ).scalars()
    )
    return province, indicator, tuple(districts)


def _definition(indicator_id: str) -> DecisionDefinition:
    return DecisionDefinition(
        identifier="market-demand-e2e",
        name="Market Demand E2E",
        description="Controlled real-data validation.",
        version="market-demand-e2e-v1",
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


def _request(definition: DecisionDefinition) -> DecisionRequest:
    return DecisionRequest(
        decision_definition_id=definition.identifier,
        original_question="Real-data market demand validation",
        geographic_scope="LP",
        reference_year=2022,
        decision_constraints={"require_provenance": True},
    )


async def _resolved_data(db_session, indicator, districts):
    definition = _definition(str(indicator.id))
    request = _request(definition)
    alternatives = tuple(
        DecisionAlternative(
            identifier=str(district.id),
            display_name=district.name,
            alternative_type="district",
            metadata={"district_code": district.code, "province_code": "LP"},
        )
        for district in districts
    )
    resolver = DecisionEvidenceResolver(db_session)
    resolutions = tuple(
        [
            await resolver.resolve(
                definition.criteria[0].indicator_requirements[0], alternative, request
            )
            for alternative in alternatives
        ]
    )
    assert all(item.status is EvidenceResolutionStatus.RESOLVED for item in resolutions)
    return definition, request, alternatives, tuple(item.evidence for item in resolutions)


@pytest.mark.asyncio
async def test_real_luapula_business_location_end_to_end(db_session, real_luapula):
    province, indicator, districts = real_luapula
    assert len(districts) == 12
    assert tuple(district.code for district in districts) == EXPECTED_CODES
    assert all(district.province_id == province.id for district in districts)

    definition, request, alternatives, evidence = await _resolved_data(
        db_session, indicator, districts
    )
    assert len(evidence) == 12
    assert all(item.reference_year == 2022 and item.unit == "People" for item in evidence)
    assert all(item.quality is EvidenceQuality.UNKNOWN for item in evidence)
    mansa = next(item for item in evidence if item.geography_name == "Mansa")
    assert mansa.raw_value == 329622.0
    assert mansa.geographic_level is GeographicLevel.DISTRICT
    assert mansa.dataset_name == "2022 Census of Population and Housing - Luapula District"
    assert mansa.source_institution == "Zambia Statistics Agency (ZamStats)"
    assert mansa.source_reference and "zamstats.gov.zm" in mansa.source_reference
    assert mansa.freshness_status is FreshnessStatus.CURRENT

    portfolio = build_business_location_evidence_portfolio(
        get_business_category_profile("supermarket")
    )
    assert portfolio.readiness_percentage == pytest.approx(25.0)
    assert portfolio.blocking_criteria == (
        "market_growth",
        "purchasing_power",
        "accessibility",
        "competition",
        "operating_feasibility",
    )
    assert tuple(item.criterion_id for item in portfolio.backlog) == portfolio.blocking_criteria

    exploratory = build_business_location_run(
        BusinessLocationRequest(
            business_category="supermarket",
            province_code="LP",
            original_question="Where is demand highest?",
            reference_year=2022,
            mode=BusinessLocationMode.EXPLORATORY,
        ),
        alternatives,
        tuple(item.model_copy(update={"indicator_id": "market_demand"}) for item in evidence),
    )
    assert (
        tuple(score.alternative.display_name for score in exploratory.decision.criterion_scores)
        == EXPECTED_RANKING
    )
    assert "not a production-grade recommendation" in " ".join(
        exploratory.decision.explanation.limitations
    )
    assert exploratory.decision.confidence.methodology_version == "confidence-v1"
    assert exploratory.decision.confidence.evidence_completeness == pytest.approx(1.0)
    assert exploratory.decision.confidence.freshness == pytest.approx(1.0)
    assert exploratory.decision.confidence.source_quality == pytest.approx(0.0)
    assert exploratory.decision.confidence.score == pytest.approx(2 / 3)
    assert exploratory.decision.sensitivity is not None
    assert exploratory.decision.sensitivity.stable_recommendation is True
    assert all(case.leader_changed is False for case in exploratory.decision.sensitivity.cases)
    normalized = min_max_normalize(
        tuple(item.raw_value for item in evidence), CriterionDirection.HIGHER_IS_BETTER
    ).values
    assert min(normalized) == 0.0
    assert max(normalized) == 1.0
    assert all(0.0 <= value <= 1.0 for value in normalized)
    for score in exploratory.decision.criterion_scores:
        component = score.criterion_scores[0]
        assert score.final_score == pytest.approx(component.weighted_contribution)
        assert component.effective_weight == pytest.approx(1.0)

    production = build_business_location_run(
        BusinessLocationRequest(
            business_category="supermarket",
            province_code="LP",
            original_question="Where should we locate?",
            reference_year=2022,
        ),
        alternatives,
        tuple(item.model_copy(update={"indicator_id": "market_demand"}) for item in evidence),
    )
    assert production.decision.recommendation is None
    assert production.decision.readiness.state.value == "insufficient_evidence"
    assert production.decision.ranking == ()
    assert production.evidence_portfolio.blocking_criteria == portfolio.blocking_criteria
    assert "No recommendation" in production.decision.explanation.why_winner_ranked_first

    repeated = build_business_location_run(
        BusinessLocationRequest(
            business_category="supermarket",
            province_code="LP",
            original_question="Where is demand highest?",
            reference_year=2022,
            mode=BusinessLocationMode.EXPLORATORY,
        ),
        alternatives,
        tuple(item.model_copy(update={"indicator_id": "market_demand"}) for item in evidence),
    )
    assert exploratory == repeated


@pytest.mark.asyncio
async def test_real_data_failure_injections_abstain(db_session, real_luapula):
    _, indicator, districts = real_luapula
    definition, request, alternatives, evidence = await _resolved_data(
        db_session, indicator, districts
    )
    production_definition = _definition("market_demand")
    production_request = _request(production_definition)
    production_evidence = tuple(
        item.model_copy(update={"indicator_id": "market_demand"}) for item in evidence
    )

    cases = (
        (
            production_evidence[:-1],
            AbstentionReasonCode.INSUFFICIENT_REQUIRED_EVIDENCE,
        ),
        (
            production_evidence[:-1]
            + (production_evidence[-1].model_copy(update={"geography_id": "wrong"}),),
            AbstentionReasonCode.INSUFFICIENT_REQUIRED_EVIDENCE,
        ),
        (
            production_evidence[:-1]
            + (production_evidence[-1].model_copy(update={"reference_year": 2020}),),
            AbstentionReasonCode.INCOMPARABLE_PERIODS,
        ),
        (
            production_evidence[:-1]
            + (
                production_evidence[-1].model_copy(
                    update={
                        "freshness_status": FreshnessStatus.STALE,
                        "freshness_date": date.today() - timedelta(days=1000),
                    }
                ),
            ),
            AbstentionReasonCode.STALE_REQUIRED_EVIDENCE,
        ),
        (
            production_evidence + (production_evidence[0],),
            AbstentionReasonCode.DUPLICATE_EVIDENCE,
        ),
        (
            production_evidence[:-1]
            + (production_evidence[-1].model_copy(update={"source_reference": None}),),
            AbstentionReasonCode.INCOMPLETE_PROVENANCE,
        ),
    )
    for injected, reason in cases:
        run_request = (
            production_request.model_copy(update={"max_evidence_age_days": 1})
            if reason is AbstentionReasonCode.STALE_REQUIRED_EVIDENCE
            else production_request
        )
        run = build_decision_run(production_definition, run_request, alternatives, injected)
        assert run.recommendation is None
        assert run.readiness.state.value == "insufficient_evidence"
        assert reason in run.readiness.reasons or (
            reason is AbstentionReasonCode.INSUFFICIENT_REQUIRED_EVIDENCE
            and AbstentionReasonCode.INSUFFICIENT_CRITERION_COVERAGE in run.readiness.reasons
        )
