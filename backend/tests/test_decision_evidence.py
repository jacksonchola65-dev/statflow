from __future__ import annotations

from datetime import date, datetime, timezone
from uuid import uuid4

import pytest
import pytest_asyncio
from app.domain.decision import (
    CriterionDirection,
    DecisionAlternative,
    DecisionCriterion,
    DecisionDefinition,
    DecisionReadiness,
    DecisionRequest,
    EvidenceResolutionStatus,
    GeographicLevel,
    IndicatorRequirement,
    build_decision_run,
)
from app.models.data_point import DataPoint
from app.models.dataset import Dataset
from app.models.indicator import Indicator
from app.models.province import Province
from app.services.decision_evidence import DecisionEvidenceResolver


@pytest_asyncio.fixture
async def provenance_records(db_session):
    province = Province(code=f"PV{uuid4().hex[:6]}", name=f"Evidence Province {uuid4().hex[:6]}")
    dataset = Dataset(
        name=f"Evidence Dataset {uuid4().hex[:8]}",
        description="Controlled provenance test dataset",
        source_name="Controlled Statistical Office",
        source_url="https://example.test/source/evidence",
        reference_year=2025,
        is_published=True,
        updated_at=datetime(2025, 12, 31, tzinfo=timezone.utc),
    )
    category = (
        await db_session.execute(
            __import__("sqlalchemy")
            .select(__import__("app.models.category", fromlist=["Category"]).Category)
            .limit(1)
        )
    ).scalar_one()
    indicator = Indicator(
        category_id=category.id,
        code=f"EVID_{uuid4().hex[:8]}",
        name="Synthetic evidence indicator",
        description="Controlled indicator",
        unit="synthetic-units",
        source_name="Controlled Statistical Office",
    )
    db_session.add_all([province, dataset, indicator])
    await db_session.flush()
    point = DataPoint(
        dataset_id=dataset.id,
        indicator_id=indicator.id,
        province_id=province.id,
        value=80,
        reference_year=2025,
    )
    db_session.add(point)
    await db_session.flush()
    return province, dataset, indicator, point


def requirement(indicator_id: str, level: GeographicLevel = GeographicLevel.PROVINCE):
    return IndicatorRequirement(
        indicator_id=indicator_id,
        name="Synthetic evidence indicator",
        geographic_level=level,
    )


def request(year: int | None = 2025, max_age: int | None = None) -> DecisionRequest:
    return DecisionRequest(
        decision_definition_id="evidence-test",
        original_question="Controlled evidence resolution test",
        reference_year=year,
        max_evidence_age_days=max_age,
    )


def alternative(province_id: str, level: str = "province") -> DecisionAlternative:
    return DecisionAlternative(
        identifier=province_id,
        display_name="Evidence Province",
        alternative_type=level,
    )


@pytest.mark.asyncio
async def test_resolves_complete_legacy_provenance_chain(db_session, provenance_records):
    province, dataset, indicator, point = provenance_records
    result = await DecisionEvidenceResolver(db_session).resolve(
        requirement(str(indicator.id)), alternative(str(province.id)), request()
    )
    assert result.status is EvidenceResolutionStatus.RESOLVED
    evidence = result.evidence
    assert evidence is not None
    assert evidence.indicator_id == str(indicator.id)
    assert evidence.indicator_name == indicator.name
    assert evidence.raw_value == 80
    assert evidence.unit == indicator.unit
    assert evidence.geography_id == str(province.id)
    assert evidence.geography_name == province.name
    assert evidence.geographic_level is GeographicLevel.PROVINCE
    assert evidence.reference_year == point.reference_year
    assert evidence.dataset_id == str(dataset.id)
    assert evidence.dataset_name == dataset.name
    assert evidence.source_institution == dataset.source_name
    assert evidence.source_reference == dataset.source_url
    assert evidence.quality.value == "unknown"
    assert evidence.freshness_status.value == "current"


@pytest.mark.asyncio
async def test_wrong_geography_level_is_rejected(db_session, provenance_records):
    province, _, indicator, _ = provenance_records
    result = await DecisionEvidenceResolver(db_session).resolve(
        requirement(str(indicator.id), GeographicLevel.DISTRICT),
        alternative(str(province.id)),
        request(),
    )
    assert result.status is EvidenceResolutionStatus.GEOGRAPHICALLY_INCOMPATIBLE


@pytest.mark.asyncio
async def test_temporal_mismatch_and_freshness_status_are_explicit(db_session, provenance_records):
    province, _, indicator, _ = provenance_records
    resolver = DecisionEvidenceResolver(db_session)
    temporal = await resolver.resolve(
        requirement(str(indicator.id)), alternative(str(province.id)), request(year=2018)
    )
    assert temporal.status is EvidenceResolutionStatus.TEMPORALLY_INCOMPATIBLE
    stale = await resolver.resolve(
        requirement(str(indicator.id)),
        alternative(str(province.id)),
        request(max_age=1),
        as_of=date(2026, 1, 10),
    )
    assert stale.status is EvidenceResolutionStatus.STALE


@pytest.mark.asyncio
async def test_resolution_is_deterministic_and_consumable_by_decision_engine(
    db_session, provenance_records
):
    province, _, indicator, _ = provenance_records
    resolver = DecisionEvidenceResolver(db_session)
    first = await resolver.resolve(
        requirement(str(indicator.id)), alternative(str(province.id)), request()
    )
    second = await resolver.resolve(
        requirement(str(indicator.id)), alternative(str(province.id)), request()
    )
    assert first == second
    assert first.evidence is not None

    definition = DecisionDefinition(
        identifier="evidence-test",
        name="Evidence Test",
        description="Synthetic integration model",
        version="1",
        geographic_level=GeographicLevel.PROVINCE,
        criteria=(
            DecisionCriterion(
                identifier="demand",
                name="Demand",
                direction=CriterionDirection.HIGHER_IS_BETTER,
                weight=1.0,
                indicator_requirements=(requirement(str(indicator.id)),),
            ),
        ),
    )
    run = build_decision_run(
        definition,
        request(),
        (alternative(str(province.id)),),
        (first.evidence,),
        confidence={"level": "initial"},
    )
    assert run.recommendation is None
    assert run.readiness.state is DecisionReadiness.INSUFFICIENT_EVIDENCE
