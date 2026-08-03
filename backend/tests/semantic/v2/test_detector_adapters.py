from app.semantic.detectors.base import DetectorInput
from app.semantic.detectors.dictionary_detector import DictionarySemanticDetector
from app.semantic.detectors.regex_detector import RegexSemanticDetector
from app.semantic.detectors.value_sampling_detector import ValueSamplingDetector
from app.semantic.v2.detector_adapters import (
    DictionaryDetectorAdapter,
    RegexDetectorAdapter,
    ValueSamplingDetectorAdapter,
)
from app.semantic.v2.feature_extraction import FeatureExtractionPipeline
from app.semantic.v2.semantic_context import SemanticContext


def _build_context_from_raw(column_name, raw_values):
    ctx = FeatureExtractionPipeline.extract(column_name, tuple(raw_values)) if False else None
    # build minimal ColumnFeatureContext via feature extraction
    ctx = FeatureExtractionPipeline.extract(column_name, tuple(raw_values))
    return ctx


def _run_v1_regex(values):
    det = RegexSemanticDetector()
    inp = DetectorInput(column_name="c", values=tuple(values))
    return det.detect(inp)


def _run_adapter_regex(ctx, idx):
    adapter = RegexDetectorAdapter()
    return adapter.detect(ctx, idx)


def test_regex_parity_email():
    raws = (" test@example.com ", "user@domain.org")
    col = FeatureExtractionPipeline.extract("c", raws)
    ctx = SemanticContext(columns=(col,))
    r1 = _run_v1_regex(raws)
    r2 = _run_adapter_regex(ctx, 0)
    assert r1 == r2


def test_dictionary_parity():
    det = DictionarySemanticDetector()
    adapter = DictionaryDetectorAdapter()
    # use known alias from SEMANTIC_DICTIONARY such as 'Email' (depends on project data)
    inp = DetectorInput(column_name="email", values=())
    v1 = det.detect(inp)
    # build context with same column name
    col = FeatureExtractionPipeline.extract("email", ())
    ctx = SemanticContext(columns=(col,))
    v2 = adapter.detect(ctx, 0)
    assert v1 == v2


def test_value_sampling_parity_integers():
    raws = ("1", "2", "3")
    col = FeatureExtractionPipeline.extract("c", raws)
    ctx = SemanticContext(columns=(col,))
    det = ValueSamplingDetector()
    v1 = det.detect(DetectorInput(column_name="c", values=tuple(raws)))
    adapter = ValueSamplingDetectorAdapter()
    v2 = adapter.detect(ctx, 0)
    assert v1 == v2
