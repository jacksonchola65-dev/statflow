from dataclasses import dataclass
from typing import Tuple, Any, List
import re
import math
from time import perf_counter

from app.semantic.detectors.base import DetectorInput, DetectorResult, SemanticDetector
from app.semantic.semantic_models import SemanticClassification
from app.semantic.semantic_types import SemanticType

# Compiled regex patterns (module-level, immutable)
_PATTERNS = (
    (SemanticType.EMAIL, re.compile(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$")),
    (SemanticType.PHONE, re.compile(r"^\+?\d[\d \-\(\)]{6,}\d$")),
    (SemanticType.URL, re.compile(r"^(https?://)?[A-Za-z0-9.-]+\.[A-Za-z]{2,}(/.*)?$")),
    (SemanticType.DATETIME, re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:Z|[+\-]\d{2}:\d{2})?$")),
    (SemanticType.DATE, re.compile(r"^\d{4}-\d{2}-\d{2}$")),
    (SemanticType.TIME, re.compile(r"^\d{2}:\d{2}(?::\d{2})?$")),
    (SemanticType.LATITUDE, re.compile(r"^-?\d{1,2}\.\d+$")),
    (SemanticType.LONGITUDE, re.compile(r"^-?\d{1,3}\.\d+$")),
    (SemanticType.POSTAL_CODE, re.compile(r"^[A-Za-z0-9 \-]{3,10}$")),
)

# Quick pre-check predicates to avoid running regexes when samples lack obvious markers
_PRECHECKS = {
    SemanticType.EMAIL: lambda s: any("@" in x for x in s),
    SemanticType.PHONE: lambda s: any(any(ch.isdigit() for ch in x) for x in s),
    SemanticType.URL: lambda s: any("." in x for x in s),
    SemanticType.DATETIME: lambda s: any("T" in x for x in s),
    SemanticType.DATE: lambda s: any("-" in x and len(x) >= 8 for x in s),
    SemanticType.TIME: lambda s: any(":" in x for x in s),
    SemanticType.LATITUDE: lambda s: any("." in x for x in s),
    SemanticType.LONGITUDE: lambda s: any("." in x for x in s),
    SemanticType.POSTAL_CODE: lambda s: any(len(x) >= 3 for x in s),
}


class RegexSemanticDetector(SemanticDetector):
    NAME = "regex"

    def detect(self, input: DetectorInput) -> DetectorResult:
        return self.detect_batch([input])[0]

    def detect_batch(self, inputs: list[DetectorInput]) -> list[DetectorResult]:
        all_values: list[list[str]] = []
        for input_obj in inputs:
            vals = []
            for v in input_obj.values:
                if v is None:
                    continue
                if isinstance(v, str) and v.strip() == "":
                    continue
                vals.append(v if isinstance(v, str) else str(v))
                if len(vals) >= 100:
                    break
            all_values.append(vals)

        results: list[DetectorResult] = []
        for vals in all_values:
            classifications: List[SemanticClassification] = []
            for sem_type, pattern in _PATTERNS:
                exact_found = False
                partial_found = False
                pre = _PRECHECKS.get(sem_type)
                if pre is not None and not pre(vals):
                    continue
                for s in vals:
                    if pattern.fullmatch(s):
                        if sem_type is SemanticType.LATITUDE:
                            try:
                                f = float(s)
                                if -90.0 <= f <= 90.0:
                                    exact_found = True
                                    break
                            except Exception:
                                continue
                        elif sem_type is SemanticType.LONGITUDE:
                            try:
                                f = float(s)
                                if -180.0 <= f <= 180.0:
                                    exact_found = True
                                    break
                            except Exception:
                                continue
                        else:
                            exact_found = True
                            break
                    else:
                        if pattern.search(s):
                            partial_found = True

                if exact_found:
                    classifications.append(SemanticClassification(semantic_type=sem_type, confidence=0.95))
                elif partial_found:
                    classifications.append(SemanticClassification(semantic_type=sem_type, confidence=0.60))

            results.append(DetectorResult(detector_name=self.NAME, classifications=tuple(classifications)))

        return results
