import time
import pytest

from app.semantic.detection_pipeline import SemanticDetectionPipeline
from app.semantic.detectors.base import DetectorInput, DetectorResult
from app.semantic.semantic_models import SemanticClassification, SemanticEvidence
from app.semantic.semantic_types import SemanticType


class DummyDetector:
    def __init__(self, name, classifications=None, raise_exc=False):
        self._name = name
        self._classifications = classifications or ()
        self._raise = raise_exc

    def detect(self, input: DetectorInput):
        if self._raise:
            raise RuntimeError("detector error")
        return DetectorResult(detector_name=self._name, classifications=tuple(self._classifications))


def make_sc(st, conf, det):
    return SemanticClassification(semantic_type=st, confidence=conf, evidence=(SemanticEvidence(source=det, score=conf, description="e"),), detector=det)


def test_empty_pipeline():
    p = SemanticDetectionPipeline([])
    out = p.run(DetectorInput(column_name="c", values=()))
    assert out == []


def test_single_detector_and_consensus():
    d = DummyDetector("d1", classifications=(make_sc(SemanticType.EMAIL, 0.9, "d1"),))
    p = SemanticDetectionPipeline([d])
    out = p.run(DetectorInput(column_name="c", values=("a",)))
    assert len(out) == 1 and out[0].semantic_type == SemanticType.EMAIL


def test_multiple_detectors_and_order():
    d1 = DummyDetector("d1", classifications=(make_sc(SemanticType.EMAIL, 0.6, "d1"),))
    d2 = DummyDetector("d2", classifications=(make_sc(SemanticType.AGE, 0.8, "d2"),))
    p = SemanticDetectionPipeline([d1, d2])
    out = p.run(DetectorInput(column_name="c", values=("a",)))
    # both types present
    types = {c.semantic_type for c in out}
    assert SemanticType.EMAIL in types and SemanticType.AGE in types


def test_detector_returning_empty_result():
    d1 = DummyDetector("d1", classifications=())
    d2 = DummyDetector("d2", classifications=(make_sc(SemanticType.EMAIL, 0.8, "d2"),))
    p = SemanticDetectionPipeline([d1, d2])
    out = p.run(DetectorInput(column_name="c", values=("a",)))
    assert len(out) == 1


def test_exception_propagation():
    d1 = DummyDetector("d1", raise_exc=True)
    p = SemanticDetectionPipeline([d1])
    with pytest.raises(RuntimeError):
        p.run(DetectorInput(column_name="c", values=("a",)))


def test_deterministic_and_performance():
    # three dummy detectors
    dets = [DummyDetector(f"d{i}", classifications=(make_sc(SemanticType.TEXT, 0.5, f"d{i}"),)) for i in range(3)]
    p = SemanticDetectionPipeline(dets)
    vals = tuple(str(i) for i in range(100))
    inp = DetectorInput(column_name="c", values=vals)
    runs = 20
    timings = []
    for _ in range(runs):
        t0 = time.perf_counter()
        out = p.run(inp)
        t1 = time.perf_counter()
        timings.append(t1 - t0)
    avg = sum(timings) / len(timings)
    assert avg < 0.01
    out2 = p.run(inp)
    assert out == out2
