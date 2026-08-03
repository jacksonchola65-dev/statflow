import pytest
from app.semantic.semantic_models import (
    SemanticClassification,
    SemanticEvidence,
    SemanticSuggestion,
)
from app.semantic.semantic_types import SemanticType


def test_valid_confidence_accepts_range():
    ev = SemanticEvidence(source="detector", score=0.5, description="ok")
    s1 = SemanticSuggestion(semantic_type=SemanticType.EMAIL, confidence=0.7)
    s2 = SemanticSuggestion(semantic_type=SemanticType.PHONE, confidence=0.2)
    sc = SemanticClassification(
        semantic_type=SemanticType.EMAIL,
        confidence=0.85,
        evidence=(ev,),
        detector="d1",
        suggestions=(s2, s1),
    )
    assert sc.confidence == pytest.approx(0.85)
    assert isinstance(sc.evidence, tuple)
    assert sc.suggestions[0].confidence >= sc.suggestions[1].confidence


@pytest.mark.parametrize("val", [-0.1, 1.1])
def test_invalid_confidence_rejected(val):
    with pytest.raises(ValueError):
        SemanticClassification(semantic_type=SemanticType.TEXT, confidence=val)


def test_nan_and_infinity_rejected():
    with pytest.raises(ValueError):
        SemanticClassification(semantic_type=SemanticType.TEXT, confidence=float("nan"))
    with pytest.raises(ValueError):
        SemanticClassification(semantic_type=SemanticType.TEXT, confidence=float("inf"))


def test_evidence_ordering_and_immutability():
    e1 = SemanticEvidence(source="a", score=0.1)
    e2 = SemanticEvidence(source="b", score=0.2)
    sc = SemanticClassification(semantic_type=SemanticType.TEXT, confidence=0.5, evidence=(e1, e2))
    assert sc.evidence[0].source == "a"
    with pytest.raises((AttributeError, TypeError)):
        sc.evidence = ()


def test_suggestion_ordering_and_immutability():
    s1 = SemanticSuggestion(semantic_type=SemanticType.CITY, confidence=0.1)
    s2 = SemanticSuggestion(semantic_type=SemanticType.COUNTRY, confidence=0.9)
    sc = SemanticClassification(
        semantic_type=SemanticType.LOCATION, confidence=0.6, suggestions=(s1, s2)
    )
    assert sc.suggestions[0].confidence == pytest.approx(0.9)
    with pytest.raises((AttributeError, TypeError)):
        sc.suggestions = ()
