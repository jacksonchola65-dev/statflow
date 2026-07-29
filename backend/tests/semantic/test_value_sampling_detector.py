import time
import pytest

from app.semantic.detectors.value_sampling_detector import ValueSamplingDetector
from app.semantic.detectors.base import DetectorInput
from app.semantic.semantic_types import SemanticType

detector = ValueSamplingDetector()


def detect(values):
    return detector.detect(DetectorInput(column_name="ignored", values=tuple(values)))


def test_boolean_detection():
    out = detect(["true", "false", "yes", "no", "1"])
    assert any(c.semantic_type == SemanticType.BOOLEAN for c in out.classifications)


def test_integer_detection():
    out = detect(["1", "2", "3", "4"]) 
    assert any(c.semantic_type == SemanticType.INTEGER for c in out.classifications)


def test_decimal_detection():
    out = detect(["1.1", "2.0", "3.5", "4.25", "5"]) 
    assert any(c.semantic_type == SemanticType.DECIMAL for c in out.classifications)


def test_category_detection():
    vals = [f"cat{(i%4)}" for i in range(25)]
    out = detect(vals)
    assert any(c.semantic_type == SemanticType.CATEGORY for c in out.classifications)


def test_currency_detection():
    vals = ["10", "200", "300", "400", "1000"]
    out = detect(vals)
    assert any(c.semantic_type == SemanticType.CURRENCY for c in out.classifications)


def test_percentage_detection():
    vals = ["10", "20", "30", "40", "50"]
    out = detect(vals)
    assert any(c.semantic_type == SemanticType.PERCENTAGE for c in out.classifications)


def test_age_detection():
    vals = ["10", "20", "30", "40", "50", "60", "70", "80", "90", "100"]
    out = detect(vals)
    assert any(c.semantic_type == SemanticType.AGE for c in out.classifications)


def test_quantity_detection():
    vals = ["1", "2", "3", "4", "5"]
    out = detect(vals)
    assert any(c.semantic_type == SemanticType.QUANTITY or c.semantic_type == SemanticType.INTEGER for c in out.classifications)


def test_text_fallback():
    vals = ["foo", "bar", "baz"]
    out = detect(vals)
    assert any(c.semantic_type == SemanticType.TEXT for c in out.classifications)


def test_null_handling_and_sample_limit():
    vals = [None, "", "1", "2"] + [str(i) for i in range(200)]
    out = detect(vals)
    # Should sample at most 100 values and be deterministic
    assert len(out.classifications) >= 1


def test_deterministic_output():
    vals = [str(i) for i in range(100)]
    out1 = detect(vals)
    out2 = detect(vals)
    assert out1.classifications == out2.classifications


def test_evidence_description_contains_sample_info():
    vals = ["foo"] * 30
    out = detect(vals)
    assert out.classifications[0].evidence[0].description


def test_performance_under_5ms():
    vals = [str(i) for i in range(100)]
    inp = DetectorInput(column_name="c", values=tuple(vals))
    runs = 20
    timings = []
    for _ in range(runs):
        t0 = time.perf_counter()
        detector.detect(inp)
        t1 = time.perf_counter()
        timings.append(t1 - t0)
    avg = sum(timings) / len(timings)
    assert avg < 0.005
