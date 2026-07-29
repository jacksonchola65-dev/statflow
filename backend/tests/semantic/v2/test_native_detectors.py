from app.semantic.v2.native_detectors import ValueSamplingDetectorV2, RegexSemanticDetectorV2, DictionarySemanticDetectorV2
from app.semantic.v2.feature_extraction import FeatureExtractionPipeline
from app.semantic.detectors.value_sampling_detector import ValueSamplingDetector
from app.semantic.detectors.regex_detector import RegexSemanticDetector
from app.semantic.detectors.dictionary_detector import DictionarySemanticDetector
from app.semantic.detectors.base import DetectorInput


def test_value_sampling_v2_parity():
    raws = ("1", "2", "3")
    ctx = FeatureExtractionPipeline.extract("c", raws)
    v1 = ValueSamplingDetector().detect(DetectorInput(column_name="c", values=tuple(raws)))
    v2 = ValueSamplingDetectorV2().detect(ctx, 0)
    assert v1 == v2


def test_regex_v2_parity():
    raws = (" test@example.com ", "user@domain.org")
    ctx = FeatureExtractionPipeline.extract("c", raws)
    v1 = RegexSemanticDetector().detect(DetectorInput(column_name="c", values=tuple(raws)))
    v2 = RegexSemanticDetectorV2().detect(ctx, 0)
    assert v1 == v2


def test_dictionary_v2_parity():
    v1 = DictionarySemanticDetector().detect(DetectorInput(column_name="email", values=()))
    ctx = FeatureExtractionPipeline.extract("email", ())
    v2 = DictionarySemanticDetectorV2().detect(ctx, 0)
    assert v1 == v2
