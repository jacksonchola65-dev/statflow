from typing import List

from app.semantic.detectors.base import DetectorInput, DetectorResult, SemanticDetector
from app.semantic.semantic_dictionary import SEMANTIC_DICTIONARY
from app.semantic.semantic_models import SemanticClassification, SemanticEvidence
from app.semantic.semantic_types import SemanticType


def _normalize(s: str) -> str:
    return s.strip().lower()


def _normalize_for_alias(s: str) -> str:
    # remove spaces, underscores, hyphens for normalized alias matching
    return s.replace(" ", "").replace("_", "").replace("-", "").lower()


# Precompute alias lookup maps at module import to avoid repeated work per-detect call
_ALIAS_LOWER: dict[str, set[str]] = {}
_ALIAS_NORMALIZED: dict[str, set[str]] = {}
_ALIAS_TO_CANONICAL: dict[str, str] = {}
for sem_name, aliases in SEMANTIC_DICTIONARY:
    lowers = set(a.lower() for a in aliases)
    norms = set(_normalize_for_alias(a) for a in aliases)
    _ALIAS_LOWER[sem_name] = lowers
    _ALIAS_NORMALIZED[sem_name] = norms
    for a in aliases:
        _ALIAS_TO_CANONICAL[a.lower()] = a
        _ALIAS_TO_CANONICAL[_normalize_for_alias(a)] = a


class DictionarySemanticDetector(SemanticDetector):
    NAME = "dictionary"

    def detect(self, input: DetectorInput) -> DetectorResult:
        return self.detect_batch([input])[0]

    def detect_batch(self, inputs: list[DetectorInput]) -> list[DetectorResult]:
        results: list[DetectorResult] = []
        for input_obj in inputs:
            raw = (input_obj.column_name or "").strip()
            if not raw:
                results.append(DetectorResult(detector_name=self.NAME, classifications=()))
                continue

            raw_lower = _normalize(raw)
            raw_normalized = _normalize_for_alias(raw)

            classifications: List[SemanticClassification] = []

            for sem_name, _ in SEMANTIC_DICTIONARY:
                if raw_lower in _ALIAS_LOWER.get(sem_name, set()):
                    conf = 0.95
                    matched_alias = _ALIAS_TO_CANONICAL.get(raw_lower, raw)
                elif raw_normalized in _ALIAS_NORMALIZED.get(sem_name, set()):
                    conf = 0.90
                    matched_alias = _ALIAS_TO_CANONICAL.get(raw_normalized, raw)
                else:
                    continue

                evidence = SemanticEvidence(
                    source=self.NAME,
                    score=conf,
                    description=f"matched alias '{matched_alias}' for '{sem_name}'",
                )
                classifications.append(
                    SemanticClassification(
                        semantic_type=SemanticType[sem_name],
                        confidence=conf,
                        evidence=(evidence,),
                        detector=self.NAME,
                    )
                )

            results.append(
                DetectorResult(detector_name=self.NAME, classifications=tuple(classifications))
            )

        return results
