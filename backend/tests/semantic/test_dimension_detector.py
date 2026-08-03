import pytest
from app.semantic.analytics_role_models import DimensionType
from app.semantic.dimension_detector import DimensionColumnInput, DimensionDetector
from app.semantic.semantic_models import SemanticClassification, SemanticEvidence
from app.semantic.semantic_types import SemanticType


def sc(semantic_type, confidence):
    return SemanticClassification(
        semantic_type=semantic_type,
        confidence=confidence,
        evidence=(SemanticEvidence(source="d", score=confidence),),
    )


def test_empty_input_returns_empty_tuple():
    assert DimensionDetector.discover(()) == ()


def test_malformed_input_raises_type_error():
    with pytest.raises(TypeError):
        DimensionDetector.discover(None)
    with pytest.raises(TypeError):
        DimensionDetector.discover(("bad",))


def test_dimension_mapping_all_types():
    cols = [
        DimensionColumnInput(column_name="date", classifications=(sc(SemanticType.DATE, 0.7),)),
        DimensionColumnInput(column_name="dt", classifications=(sc(SemanticType.DATETIME, 0.7),)),
        DimensionColumnInput(column_name="year", classifications=(sc(SemanticType.YEAR, 0.7),)),
        DimensionColumnInput(
            column_name="country", classifications=(sc(SemanticType.COUNTRY, 0.7),)
        ),
        DimensionColumnInput(column_name="city", classifications=(sc(SemanticType.CITY, 0.7),)),
        DimensionColumnInput(
            column_name="province", classifications=(sc(SemanticType.PROVINCE, 0.7),)
        ),
        DimensionColumnInput(
            column_name="district", classifications=(sc(SemanticType.DISTRICT, 0.7),)
        ),
        DimensionColumnInput(column_name="person", classifications=(sc(SemanticType.PERSON, 0.7),)),
        DimensionColumnInput(
            column_name="org", classifications=(sc(SemanticType.ORGANIZATION, 0.7),)
        ),
        DimensionColumnInput(column_name="id", classifications=(sc(SemanticType.IDENTIFIER, 0.7),)),
        DimensionColumnInput(column_name="flag", classifications=(sc(SemanticType.BOOLEAN, 0.7),)),
        DimensionColumnInput(
            column_name="category", classifications=(sc(SemanticType.CATEGORY, 0.7),)
        ),
        DimensionColumnInput(
            column_name="text", classifications=(sc(SemanticType.TEXT, 0.7),), cardinality_ratio=0.2
        ),
    ]
    result = DimensionDetector.discover(tuple(cols))
    assert len(result) == 13
    assert {d.name: d.dimension_type for d in result}["date"] == DimensionType.TEMPORAL
    assert {d.name: d.dimension_type for d in result}["country"] == DimensionType.GEOGRAPHIC
    assert {d.name: d.dimension_type for d in result}["org"] == DimensionType.ENTITY
    assert {d.name: d.dimension_type for d in result}["id"] == DimensionType.IDENTIFIER
    assert {d.name: d.dimension_type for d in result}["flag"] == DimensionType.BOOLEAN
    assert {d.name: d.dimension_type for d in result}["category"] == DimensionType.CATEGORICAL
    assert {d.name: d.dimension_type for d in result}["text"] == DimensionType.TEXTUAL


def test_thresholds_and_null_ratio():
    c1 = DimensionColumnInput(
        column_name="low", classifications=(sc(SemanticType.DATE, 0.7),), null_ratio=0.5
    )
    c2 = DimensionColumnInput(
        column_name="high", classifications=(sc(SemanticType.DATE, 0.7),), null_ratio=0.51
    )
    c3 = DimensionColumnInput(
        column_name="lowconf",
        classifications=(sc(SemanticType.DATE, 0.59),),
    )
    result = DimensionDetector.discover((c1, c2, c3))
    assert len(result) == 1
    assert result[0].name == "low"


def test_text_cardinality_rule():
    c1 = DimensionColumnInput(
        column_name="text_ok", classifications=(sc(SemanticType.TEXT, 0.7),), cardinality_ratio=0.5
    )
    c2 = DimensionColumnInput(
        column_name="text_bad",
        classifications=(sc(SemanticType.TEXT, 0.7),),
        cardinality_ratio=0.51,
    )
    result = DimensionDetector.discover((c1, c2))
    assert len(result) == 1
    assert result[0].name == "text_ok"


def test_unsupported_types_ignored():
    c1 = DimensionColumnInput(
        column_name="curr",
        classifications=(sc(SemanticType.CURRENCY, 0.9),),
    )
    c2 = DimensionColumnInput(
        column_name="qty",
        classifications=(sc(SemanticType.QUANTITY, 0.9),),
    )
    c3 = DimensionColumnInput(
        column_name="pct",
        classifications=(sc(SemanticType.PERCENTAGE, 0.9),),
    )
    assert DimensionDetector.discover((c1, c2, c3)) == ()


def test_highest_classification_selection_and_tie_break():
    c = DimensionColumnInput(
        column_name="col",
        classifications=(
            sc(SemanticType.DATE, 0.61),
            sc(SemanticType.CATEGORY, 0.61),
        ),
    )
    result = DimensionDetector.discover((c,))
    assert len(result) == 1
    assert result[0].semantic_type == SemanticType.CATEGORY


def test_duplicate_suppression_first_occurrence_wins():
    c1 = DimensionColumnInput(
        column_name="dup",
        classifications=(sc(SemanticType.COUNTRY, 0.7),),
    )
    c2 = DimensionColumnInput(
        column_name="dup",
        classifications=(sc(SemanticType.CITY, 0.9),),
    )
    result = DimensionDetector.discover((c1, c2))
    assert len(result) == 1
    assert result[0].semantic_type == SemanticType.COUNTRY


def test_evidence_preservation():
    evidence = SemanticEvidence(source="d", score=0.8, description="e")
    c = DimensionColumnInput(
        column_name="x",
        classifications=(
            SemanticClassification(
                semantic_type=SemanticType.DATE,
                confidence=0.8,
                evidence=(evidence,),
            ),
        ),
    )
    result = DimensionDetector.discover((c,))
    assert result[0].evidence == (evidence,)


def test_sorting_and_immutability():
    c1 = DimensionColumnInput(
        column_name="b",
        classifications=(sc(SemanticType.COUNTRY, 0.8),),
    )
    c2 = DimensionColumnInput(
        column_name="a",
        classifications=(sc(SemanticType.CITY, 0.8),),
    )
    c3 = DimensionColumnInput(
        column_name="c",
        classifications=(sc(SemanticType.CATEGORY, 0.7),),
    )
    cols = [c1, c2, c3]
    result = DimensionDetector.discover(cols)
    assert [d.name for d in result] == ["a", "b", "c"]
    assert cols == [c1, c2, c3]
