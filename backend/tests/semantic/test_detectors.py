import pytest
from app.semantic.detectors.base import DetectorInput, DetectorResult, SemanticDetector
from app.semantic.semantic_models import SemanticClassification, SemanticType


def test_detector_input_immutability_and_tuple_values():
    inp = DetectorInput(column_name="col", values=(1, 2, 3), inferred_type="INTEGER")
    assert isinstance(inp.values, tuple)
    with pytest.raises((AttributeError, TypeError)):
        inp.column_name = "other"


def test_detector_result_immutability():
    sc = SemanticClassification(semantic_type=SemanticType.TEXT, confidence=0.5)
    res = DetectorResult(detector_name="d", classifications=(sc,))
    assert isinstance(res.classifications, tuple)
    with pytest.raises((AttributeError, TypeError)):
        res.detector_name = "x"


def test_abstract_detector_enforced():
    with pytest.raises(TypeError):
        SemanticDetector()


def test_detector_return_contract():
    class DummyDetector(SemanticDetector):
        def detect(self, input: DetectorInput) -> DetectorResult:
            return DetectorResult(detector_name="dummy", classifications=())

    d = DummyDetector()
    inp = DetectorInput(column_name="c", values=("a",))
    out = d.detect(inp)
    assert isinstance(out, DetectorResult)
    assert out.detector_name == "dummy"
