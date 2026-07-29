import time
import pytest
from uuid import uuid4

from app.semantic.detectors.regex_detector import RegexSemanticDetector
from app.semantic.detectors.base import DetectorInput
from app.semantic.semantic_types import SemanticType


detector = RegexSemanticDetector()


def test_email_detection():
    inp = DetectorInput(column_name="c", values=("user@example.com",))
    out = detector.detect(inp)
    assert any(cl.semantic_type == SemanticType.EMAIL and cl.confidence == pytest.approx(0.95) for cl in out.classifications)


def test_phone_detection():
    inp = DetectorInput(column_name="c", values=("+1 (555) 123-4567",))
    out = detector.detect(inp)
    assert any(cl.semantic_type == SemanticType.PHONE for cl in out.classifications)


def test_url_detection():
    inp = DetectorInput(column_name="c", values=("https://example.com/path",))
    out = detector.detect(inp)
    assert any(cl.semantic_type == SemanticType.URL for cl in out.classifications)


def test_date_detection():
    inp = DetectorInput(column_name="c", values=("2023-07-27",))
    out = detector.detect(inp)
    assert any(cl.semantic_type == SemanticType.DATE for cl in out.classifications)


def test_datetime_detection():
    inp = DetectorInput(column_name="c", values=("2023-07-27T12:34:56Z",))
    out = detector.detect(inp)
    assert any(cl.semantic_type == SemanticType.DATETIME for cl in out.classifications)


def test_lat_long_detection():
    inp = DetectorInput(column_name="c", values=("-33.865143", "151.209900"))
    out = detector.detect(inp)
    assert any(cl.semantic_type == SemanticType.LATITUDE for cl in out.classifications)
    assert any(cl.semantic_type == SemanticType.LONGITUDE for cl in out.classifications)


def test_postal_code_detection():
    inp = DetectorInput(column_name="c", values=("12345",))
    out = detector.detect(inp)
    assert any(cl.semantic_type == SemanticType.POSTAL_CODE for cl in out.classifications)


def test_null_and_empty_ignored():
    inp = DetectorInput(column_name="c", values=(None, "", "user@example.com"))
    out = detector.detect(inp)
    assert any(cl.semantic_type == SemanticType.EMAIL for cl in out.classifications)


def test_mixed_values_and_multiple_matches():
    vals = ("user@example.com", "https://example.com", "2023-07-27")
    inp = DetectorInput(column_name="c", values=vals)
    out = detector.detect(inp)
    types = {cl.semantic_type for cl in out.classifications}
    assert SemanticType.EMAIL in types and SemanticType.URL in types and SemanticType.DATE in types


def test_deterministic_output():
    vals = tuple(f"user{i}@example.com" for i in range(10))
    inp = DetectorInput(column_name="c", values=vals)
    a = detector.detect(inp)
    b = detector.detect(inp)
    assert a.classifications == b.classifications


def test_performance_sampling_under_5ms():
    # 100 sampled values
    vals = tuple(f"user{i}@example.com" for i in range(100))
    inp = DetectorInput(column_name="c", values=vals)
    runs = 20
    timings = []
    for _ in range(runs):
        t0 = time.perf_counter()
        detector.detect(inp)
        t1 = time.perf_counter()
        timings.append(t1 - t0)
    avg = sum(timings) / len(timings)
    assert avg < 0.005
