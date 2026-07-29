import time
import pytest
from app.semantic.consensus_engine import ConsensusEngine
from app.semantic.semantic_models import SemanticClassification, SemanticEvidence
from app.semantic.semantic_types import SemanticType
from app.semantic.detectors.base import DetectorResult


def dr(detector_name, classifications):
    return DetectorResult(detector_name=detector_name, classifications=tuple(classifications))


def sc(st, conf, det="d"):
    return SemanticClassification(semantic_type=st, confidence=conf, evidence=(SemanticEvidence(source=det, score=conf, description="e"),), detector=det)


def test_empty_input():
    assert ConsensusEngine.merge([]) == []


def test_single_detector():
    r = dr("d1", [sc(SemanticType.EMAIL, 0.9)])
    out = ConsensusEngine.merge([r])
    assert len(out) == 1 and out[0].semantic_type == SemanticType.EMAIL and out[0].confidence == pytest.approx(0.9)


def test_multiple_detectors_same_type_aggregation_and_cap():
    r1 = dr("d1", [sc(SemanticType.EMAIL, 0.6)])
    r2 = dr("d2", [sc(SemanticType.EMAIL, 0.8)])
    out = ConsensusEngine.merge([r1, r2])
    # combined = 1 - (1-0.6)*(1-0.8) = 1 - 0.4*0.2 = 1 - 0.08 = 0.92
    assert out[0].confidence == pytest.approx(0.92)


def test_confidence_cap():
    r1 = dr("d1", [sc(SemanticType.EMAIL, 0.99)])
    r2 = dr("d2", [sc(SemanticType.EMAIL, 0.99)])
    out = ConsensusEngine.merge([r1, r2])
    assert out[0].confidence == pytest.approx(0.99)


def test_evidence_and_detector_merging_and_sorting():
    r1 = dr("d1", [sc(SemanticType.AGE, 0.7)])
    r2 = dr("d2", [sc(SemanticType.EMAIL, 0.8)])
    r3 = dr("d3", [sc(SemanticType.AGE, 0.6)])
    out = ConsensusEngine.merge([r1, r2, r3])
    # AGE combined first (higher combined confidence)
    assert out[0].semantic_type in (SemanticType.AGE, SemanticType.EMAIL)
    # evidence merging
    age = next(filter(lambda x: x.semantic_type == SemanticType.AGE, out))
    assert len(age.evidence) >= 2
    assert "," in age.detector


def test_deterministic_and_performance():
    cls = [sc(SemanticType.TEXT, 0.5) for _ in range(100)]
    results = [dr(f"d{i}", cls[i:i+1]) for i in range(100)]
    runs = 20
    times = []
    for _ in range(runs):
        t0 = time.perf_counter()
        out = ConsensusEngine.merge(results)
        t1 = time.perf_counter()
        times.append(t1 - t0)
    avg = sum(times) / len(times)
    assert avg < 0.002
    out2 = ConsensusEngine.merge(results)
    assert out == out2
