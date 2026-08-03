from __future__ import annotations

from app.semantic.detectors.base import DetectorInput, DetectorResult
from app.semantic.detectors.dictionary_detector import DictionarySemanticDetector
from app.semantic.detectors.regex_detector import RegexSemanticDetector
from app.semantic.detectors.value_sampling_detector import ValueSamplingDetector
from app.semantic.v2.semantic_context import SemanticContext


class RegexDetectorAdapter:
    def __init__(self):
        self._detector = RegexSemanticDetector()

    def detect(self, context: SemanticContext, column_index: int) -> DetectorResult:
        col = context.get_column(column_index)
        # build values from cleaned_value (do not use raw CSV)
        vals = tuple(v.cleaned_value for v in col.values)
        input_obj = DetectorInput(column_name=col.column_name, values=vals)
        return self._detector.detect(input_obj)


class DictionaryDetectorAdapter:
    def __init__(self):
        self._detector = DictionarySemanticDetector()

    def detect(self, context: SemanticContext, column_index: int) -> DetectorResult:
        col = context.get_column(column_index)
        # dictionary detector uses column name only
        input_obj = DetectorInput(column_name=col.column_name, values=())
        return self._detector.detect(input_obj)


class ValueSamplingDetectorAdapter:
    def __init__(self):
        self._detector = ValueSamplingDetector()

    def detect(self, context: SemanticContext, column_index: int) -> DetectorResult:
        col = context.get_column(column_index)
        # supply cleaned strings only
        vals = tuple(v.cleaned_value for v in col.values)
        input_obj = DetectorInput(column_name=col.column_name, values=vals)
        return self._detector.detect(input_obj)


__all__ = ["RegexDetectorAdapter", "DictionaryDetectorAdapter", "ValueSamplingDetectorAdapter"]
