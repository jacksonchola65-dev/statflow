import pytest
from app.semantic.analytics_role_models import (
    Aggregation,
    AnalyticsRoleProfile,
    DimensionCandidate,
    DimensionType,
    MeasureCandidate,
)
from app.semantic.semantic_models import SemanticEvidence
from app.semantic.semantic_types import SemanticType


def ev(source="detector", score=0.8, description="evidence"):
    return SemanticEvidence(source=source, score=score, description=description)


def test_measure_candidate_valid_fields_and_trim():
    mc = MeasureCandidate(
        name="  total sales  ",
        semantic_type=SemanticType.QUANTITY,
        aggregation=Aggregation.SUM,
        confidence=0.92,
        cardinality_ratio=0.75,
        null_ratio=0.1,
        evidence=(ev("a", 0.9), ev("b", 0.85)),
    )

    assert mc.name == "total sales"
    assert mc.semantic_type == SemanticType.QUANTITY
    assert mc.aggregation == Aggregation.SUM
    assert mc.confidence == pytest.approx(0.92)
    assert mc.cardinality_ratio == pytest.approx(0.75)
    assert mc.null_ratio == pytest.approx(0.1)
    assert mc.evidence[0].source == "a"
    assert mc.evidence[1].source == "b"


def test_dimension_candidate_valid_fields_and_trim():
    dc = DimensionCandidate(
        name="  region  ",
        semantic_type=SemanticType.PROVINCE,
        dimension_type=DimensionType.GEOGRAPHIC,
        confidence=0.5,
        cardinality_ratio=0.4,
        null_ratio=0.0,
        evidence=(ev("x", 0.6),),
    )

    assert dc.name == "region"
    assert dc.dimension_type == DimensionType.GEOGRAPHIC
    assert dc.evidence[0].score == pytest.approx(0.6)


def test_profile_preserves_ordering():
    mc1 = MeasureCandidate(
        name="m1",
        semantic_type=SemanticType.INTEGER,
        aggregation=Aggregation.COUNT,
        confidence=0.2,
        cardinality_ratio=0.1,
        null_ratio=0.0,
    )
    mc2 = MeasureCandidate(
        name="m2",
        semantic_type=SemanticType.DECIMAL,
        aggregation=Aggregation.AVG,
        confidence=0.3,
        cardinality_ratio=0.5,
        null_ratio=0.0,
    )
    dc1 = DimensionCandidate(
        name="d1",
        semantic_type=SemanticType.CATEGORY,
        dimension_type=DimensionType.CATEGORICAL,
        confidence=0.7,
        cardinality_ratio=0.8,
        null_ratio=0.0,
    )
    dc2 = DimensionCandidate(
        name="d2",
        semantic_type=SemanticType.DATE,
        dimension_type=DimensionType.TEMPORAL,
        confidence=0.6,
        cardinality_ratio=0.4,
        null_ratio=0.0,
    )

    profile = AnalyticsRoleProfile(
        measure_candidates=(mc1, mc2),
        dimension_candidates=(dc1, dc2),
    )

    assert profile.measure_candidates == (mc1, mc2)
    assert profile.dimension_candidates == (dc1, dc2)


def test_measure_candidate_immutable():
    mc = MeasureCandidate(
        name="metric",
        semantic_type=SemanticType.NUMBER,
        aggregation=Aggregation.NONE,
        confidence=0.1,
        cardinality_ratio=0.2,
        null_ratio=0.3,
    )
    with pytest.raises((AttributeError, TypeError)):
        mc.name = "other"


def test_dimension_candidate_immutable():
    dc = DimensionCandidate(
        name="dimension",
        semantic_type=SemanticType.CATEGORY,
        dimension_type=DimensionType.CATEGORICAL,
        confidence=0.2,
        cardinality_ratio=0.3,
        null_ratio=0.4,
    )
    with pytest.raises((AttributeError, TypeError)):
        dc.name = "other"


def test_profile_immutable():
    profile = AnalyticsRoleProfile()
    with pytest.raises((AttributeError, TypeError)):
        profile.measure_candidates = ()


def test_invalid_aggregation_value():
    with pytest.raises(ValueError):
        MeasureCandidate(
            name="m",
            semantic_type=SemanticType.NUMBER,
            aggregation="sum",
            confidence=0.5,
            cardinality_ratio=0.1,
            null_ratio=0.0,
        )


def test_invalid_dimension_type_value():
    with pytest.raises(ValueError):
        DimensionCandidate(
            name="d",
            semantic_type=SemanticType.CATEGORY,
            dimension_type="text",
            confidence=0.5,
            cardinality_ratio=0.1,
            null_ratio=0.0,
        )


def test_confidence_invalid_nan_inf_bool():
    with pytest.raises(ValueError):
        MeasureCandidate(
            name="bad",
            semantic_type=SemanticType.NUMBER,
            aggregation=Aggregation.MAX,
            confidence=float("nan"),
            cardinality_ratio=0.1,
            null_ratio=0.0,
        )
    with pytest.raises(ValueError):
        DimensionCandidate(
            name="bad",
            semantic_type=SemanticType.CATEGORY,
            dimension_type=DimensionType.CATEGORICAL,
            confidence=float("inf"),
            cardinality_ratio=0.1,
            null_ratio=0.0,
        )
    with pytest.raises(TypeError):
        MeasureCandidate(
            name="bad",
            semantic_type=SemanticType.NUMBER,
            aggregation=Aggregation.MIN,
            confidence=True,
            cardinality_ratio=0.1,
            null_ratio=0.0,
        )


def test_ratio_invalid_nan_inf_bool():
    with pytest.raises(ValueError):
        MeasureCandidate(
            name="bad",
            semantic_type=SemanticType.NUMBER,
            aggregation=Aggregation.COUNT,
            confidence=0.5,
            cardinality_ratio=float("nan"),
            null_ratio=0.0,
        )
    with pytest.raises(ValueError):
        DimensionCandidate(
            name="bad",
            semantic_type=SemanticType.PROVINCE,
            dimension_type=DimensionType.GEOGRAPHIC,
            confidence=0.5,
            cardinality_ratio=0.1,
            null_ratio=float("inf"),
        )
    with pytest.raises(TypeError):
        DimensionCandidate(
            name="bad",
            semantic_type=SemanticType.PROVINCE,
            dimension_type=DimensionType.GEOGRAPHIC,
            confidence=0.5,
            cardinality_ratio=False,
            null_ratio=0.0,
        )


def test_semantic_type_validation():
    with pytest.raises(TypeError):
        MeasureCandidate(
            name="m",
            semantic_type="QUANTITY",
            aggregation=Aggregation.SUM,
            confidence=0.5,
            cardinality_ratio=0.1,
            null_ratio=0.0,
        )


def test_evidence_ordering_preserved():
    e1 = ev("a", 0.7)
    e2 = ev("b", 0.6)
    mc = MeasureCandidate(
        name="m",
        semantic_type=SemanticType.QUANTITY,
        aggregation=Aggregation.COUNT_DISTINCT,
        confidence=0.4,
        cardinality_ratio=0.2,
        null_ratio=0.1,
        evidence=(e1, e2),
    )
    assert mc.evidence == (e1, e2)


def test_profile_ordering_preserved():
    mc = MeasureCandidate(
        name="m",
        semantic_type=SemanticType.INTEGER,
        aggregation=Aggregation.NONE,
        confidence=0.1,
        cardinality_ratio=0.2,
        null_ratio=0.3,
    )
    dc = DimensionCandidate(
        name="d",
        semantic_type=SemanticType.CATEGORY,
        dimension_type=DimensionType.CATEGORICAL,
        confidence=0.3,
        cardinality_ratio=0.4,
        null_ratio=0.0,
    )
    profile = AnalyticsRoleProfile(measure_candidates=(mc,), dimension_candidates=(dc,))
    assert profile.measure_candidates == (mc,)
    assert profile.dimension_candidates == (dc,)
