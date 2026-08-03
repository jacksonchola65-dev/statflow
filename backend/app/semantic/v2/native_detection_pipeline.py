from __future__ import annotations

from typing import List

from app.semantic.detectors.base import DetectorResult
from app.semantic.v2.native_detectors import (
    DictionarySemanticDetectorV2,
    NativeColumnEvaluator,
    RegexSemanticDetectorV2,
    ValueSamplingDetectorV2,
)
from app.semantic.v2.semantic_context import SemanticContext


class NativeDetectionPipeline:
    def __init__(self, detectors: List = None):
        if detectors is None:
            self._detectors = [
                RegexSemanticDetectorV2(),
                DictionarySemanticDetectorV2(),
                ValueSamplingDetectorV2(),
            ]
        else:
            self._detectors = list(detectors)

    def run(self, context: SemanticContext, fused: bool = False) -> List[List[DetectorResult]]:
        # return list per column of DetectorResult in detector order (only non-empty classifications)
        if not self._detectors:
            return [[] for _ in context.columns]

        results: List[List[DetectorResult]] = [[] for _ in context.columns]
        if fused:
            evaluator = NativeColumnEvaluator()
            for idx, col in enumerate(context.columns):
                for res in evaluator.evaluate(col):
                    results[idx].append(res)
            return results

        for idx, col in enumerate(context.columns):
            for detector in self._detectors:
                res = detector.detect(col)
                if res and getattr(res, "classifications", ()):  # non-empty
                    results[idx].append(res)

        return results


__all__ = ["NativeDetectionPipeline"]
