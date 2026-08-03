from typing import List

from app.semantic.consensus_engine import ConsensusEngine
from app.semantic.detectors.base import DetectorInput, DetectorResult, SemanticDetector
from app.semantic.semantic_models import SemanticClassification


class SemanticDetectionPipeline:
    def __init__(self, detectors: List[SemanticDetector]):
        self._detectors = list(detectors)

    def run(self, input: DetectorInput) -> List[SemanticClassification]:
        if not self._detectors:
            return []

        results: List[DetectorResult] = []
        append = results.append
        for d in self._detectors:
            res = d.detect(input)
            # detector implementations return DetectorResult with empty classifications when no match
            if res and res.classifications:
                append(res)

        if not results:
            return []
        return ConsensusEngine.merge(results)

    def run_batch(self, inputs: list[DetectorInput]) -> list[list[SemanticClassification]]:
        if not self._detectors:
            return [[] for _ in inputs]
        if not inputs:
            return []

        batch_results: list[list[DetectorResult]] = [[] for _ in inputs]
        for detector in self._detectors:
            detector_results = detector.detect_batch(inputs)
            for idx, res in enumerate(detector_results):
                if res and res.classifications:
                    batch_results[idx].append(res)

        return [ConsensusEngine.merge(results) if results else [] for results in batch_results]
