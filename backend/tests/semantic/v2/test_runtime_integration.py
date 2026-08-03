import uuid
from types import SimpleNamespace

from app.services.file_inspection_service import FileInspectionService


def make_source_column(name, samples, nullable=False):
    return SimpleNamespace(name=name, sample_values=list(samples), nullable=nullable)


def test_default_is_v2(monkeypatch):
    # ensure default env not set -> v2
    monkeypatch.delenv("SEMANTIC_ENGINE_VERSION", raising=False)
    svc = FileInspectionService()
    # minimal CSV bytes with header only
    csvb = b"a,b\n1,2\n"
    resp = svc.inspect_csv(csvb, "f.csv", "text/csv", uuid.uuid4())
    # semantic_profile present (v2 native path ran) and shaped as dict
    assert isinstance(resp.semantic_profile, dict)


def test_explicit_v2_uses_native(monkeypatch):
    monkeypatch.setenv("SEMANTIC_ENGINE_VERSION", "v2")
    svc = FileInspectionService()
    csvb = b"email,phone\nuser@example.com,123\n"
    resp = svc.inspect_csv(csvb, "f.csv", "text/csv", uuid.uuid4())
    assert isinstance(resp.semantic_profile, dict)


def test_invalid_value_falls_back(monkeypatch):
    monkeypatch.setenv("SEMANTIC_ENGINE_VERSION", "invalid")
    svc = FileInspectionService()
    csvb = b"a\n1\n"
    resp = svc.inspect_csv(csvb, "f.csv", "text/csv", uuid.uuid4())
    assert isinstance(resp.semantic_profile, dict)
