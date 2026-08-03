import pytest
from app.semantic.analytics_role_models import Aggregation
from app.semantic.measure_detector import MeasureColumnInput, MeasureDetector
from app.semantic.semantic_models import SemanticClassification, SemanticEvidence
from app.semantic.semantic_types import SemanticType


def sc(semantic_type, confidence):
    return SemanticClassification(
        semantic_type=semantic_type,
        confidence=confidence,
        evidence=(SemanticEvidence(source="d", score=confidence),),
    )


def test_empty_input_returns_empty_tuple():
    assert MeasureDetector.discover(()) == ()


def test_malformed_input_raises_type_error():
    with pytest.raises(TypeError):
        MeasureDetector.discover(None)
    with pytest.raises(TypeError):
        MeasureDetector.discover(("bad",))


def test_eligible_measure_detection():
    col = MeasureColumnInput(
        column_name="sales",
        classifications=(sc(SemanticType.CURRENCY, 0.8), sc(SemanticType.TEXT, 0.9)),
        cardinality_ratio=0.5,
        null_ratio=0.1,
    )
    result = MeasureDetector.discover((col,))
    assert len(result) == 1
    assert result[0].name == "sales"
    assert result[0].semantic_type == SemanticType.CURRENCY


def test_non_measure_ignored():
    col = MeasureColumnInput(
        column_name="name",
        classifications=(sc(SemanticType.TEXT, 0.95),),
    )
    assert MeasureDetector.discover((col,)) == ()


def test_threshold_enforced():
    col = MeasureColumnInput(
        column_name="qty",
        classifications=(sc(SemanticType.QUANTITY, 0.59),),
    )
    assert MeasureDetector.discover((col,)) == ()


def test_aggregation_inference():
    c1 = MeasureColumnInput(
        column_name="c1",
        classifications=(sc(SemanticType.CURRENCY, 0.9),),
    )
    c2 = MeasureColumnInput(
        column_name="c2",
        classifications=(sc(SemanticType.PERCENTAGE, 0.75),),
    )
    c3 = MeasureColumnInput(
        column_name="c3",
        classifications=(sc(SemanticType.INTEGER, 0.8),),
    )
    result = MeasureDetector.discover((c1, c2, c3))
    assert [m.name for m in result] == ["c1", "c3", "c2"]
    assert {m.name: m.aggregation for m in result} == {
        "c1": Aggregation.SUM,
        "c2": Aggregation.AVG,
        "c3": Aggregation.SUM,
    }


def test_duplicate_suppression_first_occurrence_wins():
    c1 = MeasureColumnInput(
        column_name="m",
        classifications=(sc(SemanticType.DECIMAL, 0.8),),
    )
    c2 = MeasureColumnInput(
        column_name="m",
        classifications=(sc(SemanticType.CURRENCY, 0.9),),
    )
    result = MeasureDetector.discover((c1, c2))
    assert len(result) == 1
    assert result[0].semantic_type == SemanticType.DECIMAL
    assert result[0].confidence == pytest.approx(0.8)


def test_deterministic_sorting_by_confidence_then_name():
    c1 = MeasureColumnInput(
        column_name="b",
        classifications=(sc(SemanticType.INTEGER, 0.9),),
    )
    c2 = MeasureColumnInput(
        column_name="a",
        classifications=(sc(SemanticType.DECIMAL, 0.9),),
    )
    c3 = MeasureColumnInput(
        column_name="c",
        classifications=(sc(SemanticType.CURRENCY, 0.85),),
    )
    result = MeasureDetector.discover((c1, c2, c3))
    assert [m.name for m in result] == ["a", "b", "c"]


def test_input_immutability_preserved():
    c1 = MeasureColumnInput(
        column_name="x",
        classifications=(sc(SemanticType.QUANTITY, 0.7),),
    )
    cols = [c1]
    result = MeasureDetector.discover(cols)
    assert len(result) == 1
    assert cols == [c1]


def test_malformed_classification_iterable_raises():
    with pytest.raises(TypeError):
        MeasureColumnInput(
            column_name="x",
            classifications=("notaclass",),
        )
