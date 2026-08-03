import pytest
from app.semantic.detectors.base import DetectorInput
from app.semantic.detectors.dictionary_detector import DictionarySemanticDetector
from app.semantic.semantic_types import SemanticType

detector = DictionarySemanticDetector()


def run_det(column_name):
    return detector.detect(DetectorInput(column_name=column_name))


def test_exact_match():
    out = run_det("email")
    assert any(
        c.semantic_type == SemanticType.EMAIL and c.confidence == pytest.approx(0.95)
        for c in out.classifications
    )


def test_alias_match():
    out = run_det("e-mail")
    assert any(
        c.semantic_type == SemanticType.EMAIL and c.confidence == pytest.approx(0.95)
        for c in out.classifications
    )


def test_case_insensitive_and_whitespace_normalization():
    out = run_det("  Email  ")
    assert any(c.semantic_type == SemanticType.EMAIL for c in out.classifications)


def test_underscore_and_hyphen_normalization():
    out = run_det("postal_code")
    assert any(
        c.semantic_type == SemanticType.POSTAL_CODE and c.confidence == pytest.approx(0.95)
        for c in out.classifications
    )
    out2 = run_det("postal-code")
    assert any(c.semantic_type == SemanticType.POSTAL_CODE for c in out2.classifications)


def test_no_match():
    out = run_det("unknown_column_name")
    assert len(out.classifications) == 0


def test_multiple_aliases_and_deterministic():
    out1 = run_det("id")
    out2 = run_det("ID")
    assert out1.classifications == out2.classifications
    assert any(c.semantic_type == SemanticType.IDENTIFIER for c in out1.classifications)


def test_evidence_description_correctness():
    out = run_det("email")
    c = next(filter(lambda x: x.semantic_type == SemanticType.EMAIL, out.classifications))
    assert "matched alias" in c.evidence[0].description
