import os
import sys
import uuid
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "backend"))

from app.services.file_inspection_service import FileInspectionService
from app.services.file_inspection_service import DetectorInput, SemanticDetectionPipeline
from app.semantic.v2.feature_extraction import FeatureExtractionPipeline


def _make_csv(headers, rows):
    lines = [
        ",".join(headers),
    ]
    for row in rows:
        lines.append(",".join(row))
    return "\n".join(lines).encode("utf-8")


def _generate_wide_csv(column_count, row_count=10):
    headers = [f"col{i}" for i in range(column_count)]
    rows = [[str(i + j * 100) for i in range(column_count)] for j in range(row_count)]
    return _make_csv(headers, rows)


def _generate_mixed_csv():
    headers = ["id", "score", "email", "notes", "date"]
    rows = [
        ["1", "100", "a@example.com", "foo", "2020-01-01"],
        ["2", "", "", "bar", ""],
        ["3", "75.5", "b@example.com", "baz", "2020-02-02"],
    ]
    return _make_csv(headers, rows)


def _repr_csv_variants():
    variants = [
        _make_csv(["a", "b"], [["1", "2"], ["3", "4"]]),
        _make_csv(["text", "value"], [["foo", "100"], ["bar", "200"]]),
        _make_csv(["email", "phone"], [["user@example.com", "+123456789"], ["x@y.com", "555-1234"]]),
        _make_csv(["date", "value"], [["2020-01-01", "1"], ["2020-12-31", "2"]]),
        _make_csv(["mixed", "category"], [["100", "A"], ["foo", "A"], ["200", "B"]]),
        _make_csv(["null", "text"], [["", "one"], ["", "two"], ["", ""]]),
        _make_csv(["wide1", "wide2", "wide3", "wide4", "wide5"], [["1", "2", "3", "4", "5"]]),
        _make_csv(["alpha", "unicode"], [["náme", "テスト"], ["café", "россия"]]),
        _make_csv(["year", "amount"], [["1999", "100.00"], ["2000", "150.50"]]),
        _make_csv(["id", "code", "flag"], [["A1", "001", "true"], ["B2", "002", "false"]]),
    ]
    variants.append(_generate_wide_csv(100, row_count=5))
    variants.append(_generate_wide_csv(200, row_count=3))
    return variants


@pytest.fixture(autouse=True)
def clear_semantic_env():
    old = os.environ.pop("SEMANTIC_ENGINE_VERSION", None)
    yield
    if old is not None:
        os.environ["SEMANTIC_ENGINE_VERSION"] = old


def test_default_configuration_uses_v2():
    svc = FileInspectionService()
    resp = svc.inspect_csv(b"a,b\n1,2\n", "f.csv", "text/csv", uuid.uuid4())
    assert isinstance(resp.semantic_profile, dict)
    assert resp.semantic_profile != {}


def test_explicit_v1_uses_v1(monkeypatch):
    monkeypatch.setenv("SEMANTIC_ENGINE_VERSION", "v1")
    svc = FileInspectionService()
    resp = svc.inspect_csv(b"a,b\n1,2\n", "f.csv", "text/csv", uuid.uuid4())
    assert isinstance(resp.semantic_profile, dict)
    assert resp.semantic_profile != {}


def test_explicit_v2_uses_fused_native(monkeypatch):
    monkeypatch.setenv("SEMANTIC_ENGINE_VERSION", "v2")
    monkeypatch.setattr(DetectorInput, "__init__", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("DetectorInput should not be created in v2 path")))
    monkeypatch.setattr(SemanticDetectionPipeline, "__init__", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("v1 pipeline should not be constructed in v2 path")))
    svc = FileInspectionService()
    resp = svc.inspect_csv(b"email,phone\nuser@example.com,12345\n", "f.csv", "text/csv", uuid.uuid4())
    assert isinstance(resp.semantic_profile, dict)
    assert resp.semantic_profile != {}


def test_invalid_engine_value_falls_back_to_v1(monkeypatch):
    monkeypatch.setenv("SEMANTIC_ENGINE_VERSION", "invalid")
    called = {"v1": False}

    original_init = SemanticDetectionPipeline.__init__

    def spy_init(self, *args, **kwargs):
        called["v1"] = True
        return original_init(self, *args, **kwargs)

    monkeypatch.setattr(SemanticDetectionPipeline, "__init__", spy_init)
    svc = FileInspectionService()
    resp = svc.inspect_csv(b"a,b\n1,2\n", "f.csv", "text/csv", uuid.uuid4())
    assert called["v1"] is True
    assert isinstance(resp.semantic_profile, dict)


def test_v2_feature_extraction_and_context_construction(monkeypatch):
    monkeypatch.setenv("SEMANTIC_ENGINE_VERSION", "v2")
    calls = {"extract": 0, "context": 0}

    original_extract = FeatureExtractionPipeline.extract

    def spy_extract(column_name, values):
        calls["extract"] += 1
        return original_extract(column_name, values)

    monkeypatch.setattr(FeatureExtractionPipeline, "extract", staticmethod(spy_extract))

    from app.semantic.v2.integration import SemanticContext as IntegrationContext
    original_context_init = IntegrationContext.__init__

    def spy_context_init(self, *args, **kwargs):
        calls["context"] += 1
        return original_context_init(self, *args, **kwargs)

    monkeypatch.setattr(IntegrationContext, "__init__", spy_context_init)

    csvb = _make_csv(["a", "b", "c"], [["1", "2", "3"], ["4", "5", "6"]])
    svc = FileInspectionService()
    resp = svc.inspect_csv(csvb, "f.csv", "text/csv", uuid.uuid4())
    assert calls["extract"] == 3
    assert calls["context"] == 1
    assert isinstance(resp.semantic_profile, dict)


def test_v2_matches_v1_semantic_profile_for_representative_csvs():
    variants = _repr_csv_variants()
    svc = FileInspectionService()
    for idx, csvb in enumerate(variants):
        os.environ["SEMANTIC_ENGINE_VERSION"] = "v1"
        resp_v1 = svc.inspect_csv(csvb, "f.csv", "text/csv", uuid.uuid4())
        os.environ["SEMANTIC_ENGINE_VERSION"] = "v2"
        resp_v2 = svc.inspect_csv(csvb, "f.csv", "text/csv", uuid.uuid4())
        assert resp_v2.semantic_profile == resp_v1.semantic_profile, f"Mismatch on variant {idx}"


def test_empty_csv_raises_empty_file_error():
    svc = FileInspectionService()
    with pytest.raises(Exception):
        svc.inspect_csv(b"", "f.csv", "text/csv", uuid.uuid4())


def test_header_only_csv_returns_inspection():
    svc = FileInspectionService()
    resp = svc.inspect_csv(b"a,b,c\n", "f.csv", "text/csv", uuid.uuid4())
    assert len(resp.columns) == 3
    assert all(col.sample_values == [] for col in resp.columns)
    assert isinstance(resp.semantic_profile, dict)


def test_mixed_type_csv_inspection(monkeypatch):
    svc = FileInspectionService()
    resp = svc.inspect_csv(_generate_mixed_csv(), "f.csv", "text/csv", uuid.uuid4())
    assert isinstance(resp.semantic_profile, dict)


def test_null_heavy_csv_inspection(monkeypatch):
    csvb = _make_csv(["a", "b"], [["", ""], ["", "x"], ["", ""]])
    svc = FileInspectionService()
    resp = svc.inspect_csv(csvb, "f.csv", "text/csv", uuid.uuid4())
    assert isinstance(resp.semantic_profile, dict)


def test_wide_csv_inspection(monkeypatch):
    csvb = _generate_wide_csv(50, row_count=5)
    svc = FileInspectionService()
    resp = svc.inspect_csv(csvb, "f.csv", "text/csv", uuid.uuid4())
    assert len(resp.columns) == 50
    assert isinstance(resp.semantic_profile, dict)


def test_semantic_failure_preserves_base_inspection(monkeypatch):
    monkeypatch.setenv("SEMANTIC_ENGINE_VERSION", "v2")
    import app.services.file_inspection_service as fis

    def fail(_):
        raise RuntimeError("semantic failure")

    monkeypatch.setattr(fis, "compose_semantic_profile_from_columns", fail)
    svc = FileInspectionService()
    resp = svc.inspect_csv(b"a,b\n1,2\n", "f.csv", "text/csv", uuid.uuid4())
    assert resp.semantic_profile == {}
    assert resp.columns[0].name == "a"


def test_response_schema_unchanged_between_v1_and_v2():
    csvb = b"a,b\n1,2\n"
    svc = FileInspectionService()
    os.environ["SEMANTIC_ENGINE_VERSION"] = "v1"
    resp1 = svc.inspect_csv(csvb, "f.csv", "text/csv", uuid.uuid4())
    os.environ["SEMANTIC_ENGINE_VERSION"] = "v2"
    resp2 = svc.inspect_csv(csvb, "f.csv", "text/csv", uuid.uuid4())
    assert resp1.__class__ == resp2.__class__
    assert resp1.__dict__.keys() == resp2.__dict__.keys()
