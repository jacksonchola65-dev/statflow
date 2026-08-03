from __future__ import annotations

import re as _re
from statistics import median, pvariance

from app.semantic.detectors.base import DetectorResult
from app.semantic.detectors.dictionary_detector import (
    _ALIAS_LOWER,
    _ALIAS_NORMALIZED,
    _ALIAS_TO_CANONICAL,
)
from app.semantic.detectors.regex_detector import _PATTERNS
from app.semantic.semantic_models import SemanticClassification, SemanticEvidence
from app.semantic.semantic_types import SemanticType
from app.semantic.v2.feature_models import ColumnFeatureContext, LightValueFeatures

# Pre-import semantic dictionary metadata once to avoid repeated __import__ calls
SEMANTIC_DICTIONARY = __import__(
    "app.semantic.semantic_dictionary", fromlist=["SEMANTIC_DICTIONARY"]
).SEMANTIC_DICTIONARY
_DIGIT_RE = _re.compile(r"\d")


def _evaluate_value_sampling_values(vals: tuple[LightValueFeatures, ...]) -> DetectorResult:
    if not vals:
        return DetectorResult(detector_name=ValueSamplingDetectorV2.NAME, classifications=())

    sample_size = len(vals)

    bool_tokens = {"true", "false", "yes", "no", "y", "n", "0", "1"}
    if all((v.lowered_value in bool_tokens) for v in vals):
        ev = SemanticEvidence(
            source=ValueSamplingDetectorV2.NAME,
            score=0.95,
            description=f"sample_size={sample_size}; all values boolean-like",
        )
        return DetectorResult(
            detector_name=ValueSamplingDetectorV2.NAME,
            classifications=(
                SemanticClassification(
                    semantic_type=SemanticType.BOOLEAN,
                    confidence=0.95,
                    evidence=(ev,),
                    detector=ValueSamplingDetectorV2.NAME,
                ),
            ),
        )

    numeric_values = []
    int_count = 0
    decimal_count = 0
    within_age = 0
    in_0_100 = 0
    in_0_1 = 0
    unique_set = set()

    for v in vals:
        unique_set.add(v.cleaned_value)
        pn = v.parsed_number
        if pn is not None:
            numeric_values.append(pn)
            if not float(pn).is_integer():
                decimal_count += 1
            else:
                int_count += 1
            if 0 <= pn <= 130:
                within_age += 1
            if 0 <= pn <= 100:
                in_0_100 += 1
            if 0.0 <= pn <= 1.0:
                in_0_1 += 1

    numeric_count = len(numeric_values)

    if numeric_count > 0 and (decimal_count / numeric_count) > 0.5:
        ev = SemanticEvidence(
            source=ValueSamplingDetectorV2.NAME,
            score=0.95,
            description=f"sample_size={sample_size}; numeric_count={numeric_count}; decimal_ratio={decimal_count / numeric_count:.2f}",
        )
        return DetectorResult(
            detector_name=ValueSamplingDetectorV2.NAME,
            classifications=(
                SemanticClassification(
                    semantic_type=SemanticType.DECIMAL,
                    confidence=0.95,
                    evidence=(ev,),
                    detector=ValueSamplingDetectorV2.NAME,
                ),
            ),
        )

    if numeric_count > 0 and sample_size >= 10:
        if (within_age / numeric_count) >= 0.95:
            ev = SemanticEvidence(
                source=ValueSamplingDetectorV2.NAME,
                score=0.95,
                description=f"sample_size={sample_size}; numeric_count={numeric_count}; within_age_ratio={within_age / numeric_count:.2f}",
            )
            return DetectorResult(
                detector_name=ValueSamplingDetectorV2.NAME,
                classifications=(
                    SemanticClassification(
                        semantic_type=SemanticType.AGE,
                        confidence=0.95,
                        evidence=(ev,),
                        detector=ValueSamplingDetectorV2.NAME,
                    ),
                ),
            )

    if numeric_count > 0:
        med_val = median(numeric_values) if numeric_values else 0
        if ((in_0_100 / numeric_count) >= 0.9 or (in_0_1 / numeric_count) >= 0.9) and med_val >= 10:
            ev = SemanticEvidence(
                source=ValueSamplingDetectorV2.NAME,
                score=0.95,
                description=f"sample_size={sample_size}; numeric_count={numeric_count}; in0_100={in_0_100}; in0_1={in_0_1}",
            )
            return DetectorResult(
                detector_name=ValueSamplingDetectorV2.NAME,
                classifications=(
                    SemanticClassification(
                        semantic_type=SemanticType.PERCENTAGE,
                        confidence=0.95,
                        evidence=(ev,),
                        detector=ValueSamplingDetectorV2.NAME,
                    ),
                ),
            )

    if numeric_count == sample_size and numeric_count > 0:
        med = median(numeric_values)
        var = pvariance(numeric_values)
        if med > 100 and var > 1000:
            ev = SemanticEvidence(
                source=ValueSamplingDetectorV2.NAME,
                score=0.95,
                description=f"sample_size={sample_size}; median={med:.2f}; variance={var:.2f}",
            )
            return DetectorResult(
                detector_name=ValueSamplingDetectorV2.NAME,
                classifications=(
                    SemanticClassification(
                        semantic_type=SemanticType.CURRENCY,
                        confidence=0.95,
                        evidence=(ev,),
                        detector=ValueSamplingDetectorV2.NAME,
                    ),
                ),
            )

    if numeric_count == sample_size and int_count == numeric_count:
        ev = SemanticEvidence(
            source=ValueSamplingDetectorV2.NAME,
            score=0.95,
            description=f"sample_size={sample_size}; numeric_count={numeric_count}; all integer",
        )
        return DetectorResult(
            detector_name=ValueSamplingDetectorV2.NAME,
            classifications=(
                SemanticClassification(
                    semantic_type=SemanticType.INTEGER,
                    confidence=0.95,
                    evidence=(ev,),
                    detector=ValueSamplingDetectorV2.NAME,
                ),
            ),
        )

    if numeric_count == sample_size and all(x >= 0 for x in numeric_values):
        ev = SemanticEvidence(
            source=ValueSamplingDetectorV2.NAME,
            score=0.9,
            description=f"sample_size={sample_size}; numeric_count={numeric_count}; min={min(numeric_values):.2f}; max={max(numeric_values):.2f}",
        )
        return DetectorResult(
            detector_name=ValueSamplingDetectorV2.NAME,
            classifications=(
                SemanticClassification(
                    semantic_type=SemanticType.QUANTITY,
                    confidence=0.9,
                    evidence=(ev,),
                    detector=ValueSamplingDetectorV2.NAME,
                ),
            ),
        )

    unique_count = len(unique_set)
    unique_ratio = unique_count / sample_size
    if sample_size >= 20 and unique_ratio <= 0.20:
        ev = SemanticEvidence(
            source=ValueSamplingDetectorV2.NAME,
            score=0.95,
            description=f"sample_size={sample_size}; unique_count={unique_count}; unique_ratio={unique_ratio:.2f}",
        )
        return DetectorResult(
            detector_name=ValueSamplingDetectorV2.NAME,
            classifications=(
                SemanticClassification(
                    semantic_type=SemanticType.CATEGORY,
                    confidence=0.95,
                    evidence=(ev,),
                    detector=ValueSamplingDetectorV2.NAME,
                ),
            ),
        )

    ev = SemanticEvidence(
        source=ValueSamplingDetectorV2.NAME,
        score=0.5,
        description=f"sample_size={sample_size}; unique_count={unique_count}",
    )
    return DetectorResult(
        detector_name=ValueSamplingDetectorV2.NAME,
        classifications=(
            SemanticClassification(
                semantic_type=SemanticType.TEXT,
                confidence=0.5,
                evidence=(ev,),
                detector=ValueSamplingDetectorV2.NAME,
            ),
        ),
    )


class ValueSamplingDetectorV2:
    NAME = "value_sampling"

    def detect(self, context_or_col, column_index: int = 0) -> DetectorResult:
        # native implementation mirroring v1 ValueSamplingDetector logic
        if hasattr(context_or_col, "get_column"):
            col = context_or_col.get_column(column_index)
        else:
            col = context_or_col

        vals = col.values
        if not vals:
            return DetectorResult(detector_name=ValueSamplingDetectorV2.NAME, classifications=())

        sample_size = len(vals)

        # Boolean detection using precomputed lowered_value
        bool_tokens = {"true", "false", "yes", "no", "y", "n", "0", "1"}
        if all((v.lowered_value in bool_tokens) for v in vals):
            ev = SemanticEvidence(
                source=ValueSamplingDetectorV2.NAME,
                score=0.95,
                description=f"sample_size={sample_size}; all values boolean-like",
            )
            return DetectorResult(
                detector_name=ValueSamplingDetectorV2.NAME,
                classifications=(
                    SemanticClassification(
                        semantic_type=SemanticType.BOOLEAN,
                        confidence=0.95,
                        evidence=(ev,),
                        detector=ValueSamplingDetectorV2.NAME,
                    ),
                ),
            )

        numeric_values = []
        int_count = 0
        decimal_count = 0
        within_age = 0
        in_0_100 = 0
        in_0_1 = 0
        unique_set = set()

        for v in vals:
            unique_set.add(v.cleaned_value)
            pn = v.parsed_number
            if pn is not None:
                numeric_values.append(pn)
                if not float(pn).is_integer():
                    decimal_count += 1
                else:
                    int_count += 1
                if 0 <= pn <= 130:
                    within_age += 1
                if 0 <= pn <= 100:
                    in_0_100 += 1
                if 0.0 <= pn <= 1.0:
                    in_0_1 += 1

        numeric_count = len(numeric_values)

        # DECIMAL: majority of numeric values have decimals
        if numeric_count > 0 and (decimal_count / numeric_count) > 0.5:
            ev = SemanticEvidence(
                source=ValueSamplingDetectorV2.NAME,
                score=0.95,
                description=f"sample_size={sample_size}; numeric_count={numeric_count}; decimal_ratio={decimal_count / numeric_count:.2f}",
            )
            return DetectorResult(
                detector_name=ValueSamplingDetectorV2.NAME,
                classifications=(
                    SemanticClassification(
                        semantic_type=SemanticType.DECIMAL,
                        confidence=0.95,
                        evidence=(ev,),
                        detector=ValueSamplingDetectorV2.NAME,
                    ),
                ),
            )

        # AGE detection
        if numeric_count > 0 and sample_size >= 10:
            if (within_age / numeric_count) >= 0.95:
                ev = SemanticEvidence(
                    source=ValueSamplingDetectorV2.NAME,
                    score=0.95,
                    description=f"sample_size={sample_size}; numeric_count={numeric_count}; within_age_ratio={within_age / numeric_count:.2f}",
                )
                return DetectorResult(
                    detector_name=ValueSamplingDetectorV2.NAME,
                    classifications=(
                        SemanticClassification(
                            semantic_type=SemanticType.AGE,
                            confidence=0.95,
                            evidence=(ev,),
                            detector=ValueSamplingDetectorV2.NAME,
                        ),
                    ),
                )

        # PERCENTAGE detection
        if numeric_count > 0:
            med_val = median(numeric_values) if numeric_values else 0
            if (
                (in_0_100 / numeric_count) >= 0.9 or (in_0_1 / numeric_count) >= 0.9
            ) and med_val >= 10:
                ev = SemanticEvidence(
                    source=ValueSamplingDetectorV2.NAME,
                    score=0.95,
                    description=f"sample_size={sample_size}; numeric_count={numeric_count}; in0_100={in_0_100}; in0_1={in_0_1}",
                )
                return DetectorResult(
                    detector_name=ValueSamplingDetectorV2.NAME,
                    classifications=(
                        SemanticClassification(
                            semantic_type=SemanticType.PERCENTAGE,
                            confidence=0.95,
                            evidence=(ev,),
                            detector=ValueSamplingDetectorV2.NAME,
                        ),
                    ),
                )

        # CURRENCY detection
        if numeric_count == sample_size and numeric_count > 0:
            med = median(numeric_values)
            var = pvariance(numeric_values)
            if med > 100 and var > 1000:
                ev = SemanticEvidence(
                    source=ValueSamplingDetectorV2.NAME,
                    score=0.95,
                    description=f"sample_size={sample_size}; median={med:.2f}; variance={var:.2f}",
                )
                return DetectorResult(
                    detector_name=ValueSamplingDetectorV2.NAME,
                    classifications=(
                        SemanticClassification(
                            semantic_type=SemanticType.CURRENCY,
                            confidence=0.95,
                            evidence=(ev,),
                            detector=ValueSamplingDetectorV2.NAME,
                        ),
                    ),
                )

        # INTEGER detection
        if numeric_count == sample_size and int_count == numeric_count:
            ev = SemanticEvidence(
                source=ValueSamplingDetectorV2.NAME,
                score=0.95,
                description=f"sample_size={sample_size}; numeric_count={numeric_count}; all integer",
            )
            return DetectorResult(
                detector_name=ValueSamplingDetectorV2.NAME,
                classifications=(
                    SemanticClassification(
                        semantic_type=SemanticType.INTEGER,
                        confidence=0.95,
                        evidence=(ev,),
                        detector=ValueSamplingDetectorV2.NAME,
                    ),
                ),
            )

        # QUANTITY detection
        if numeric_count == sample_size and all(x >= 0 for x in numeric_values):
            ev = SemanticEvidence(
                source=ValueSamplingDetectorV2.NAME,
                score=0.9,
                description=f"sample_size={sample_size}; numeric_count={numeric_count}; min={min(numeric_values):.2f}; max={max(numeric_values):.2f}",
            )
            return DetectorResult(
                detector_name=ValueSamplingDetectorV2.NAME,
                classifications=(
                    SemanticClassification(
                        semantic_type=SemanticType.QUANTITY,
                        confidence=0.9,
                        evidence=(ev,),
                        detector=ValueSamplingDetectorV2.NAME,
                    ),
                ),
            )

        unique_count = len(unique_set)
        unique_ratio = unique_count / sample_size
        if sample_size >= 20 and unique_ratio <= 0.20:
            ev = SemanticEvidence(
                source=ValueSamplingDetectorV2.NAME,
                score=0.95,
                description=f"sample_size={sample_size}; unique_count={unique_count}; unique_ratio={unique_ratio:.2f}",
            )
            return DetectorResult(
                detector_name=ValueSamplingDetectorV2.NAME,
                classifications=(
                    SemanticClassification(
                        semantic_type=SemanticType.CATEGORY,
                        confidence=0.95,
                        evidence=(ev,),
                        detector=ValueSamplingDetectorV2.NAME,
                    ),
                ),
            )

        ev = SemanticEvidence(
            source=ValueSamplingDetectorV2.NAME,
            score=0.5,
            description=f"sample_size={sample_size}; unique_count={unique_count}",
        )
        return DetectorResult(
            detector_name=ValueSamplingDetectorV2.NAME,
            classifications=(
                SemanticClassification(
                    semantic_type=SemanticType.TEXT,
                    confidence=0.5,
                    evidence=(ev,),
                    detector=ValueSamplingDetectorV2.NAME,
                ),
            ),
        )


def _evaluate_regex_values(vals: tuple[str, ...]) -> DetectorResult:
    if not vals:
        return DetectorResult(detector_name=RegexSemanticDetectorV2.NAME, classifications=())

    combined = " ".join(vals)
    import re as _re

    has_at = "@" in combined
    has_digit = bool(_re.search(r"\d", combined))
    has_dot = "." in combined
    has_T = "T" in combined
    has_dash_len8 = any(("-" in s and len(s) >= 8) for s in vals)
    has_colon = ":" in combined
    has_len3 = any(len(s) >= 3 for s in vals)

    classifications = []
    for sem_type, pattern in _PATTERNS:
        exact_found = False
        partial_found = False

        if sem_type is SemanticType.EMAIL and not has_at:
            continue
        if sem_type is SemanticType.PHONE and not has_digit:
            continue
        if sem_type is SemanticType.URL and not has_dot:
            continue
        if sem_type is SemanticType.DATETIME and not has_T:
            continue
        if sem_type is SemanticType.DATE and not has_dash_len8:
            continue
        if sem_type is SemanticType.TIME and not has_colon:
            continue
        if sem_type in (SemanticType.LATITUDE, SemanticType.LONGITUDE) and not has_dot:
            continue
        if sem_type is SemanticType.POSTAL_CODE and not has_len3:
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

    return DetectorResult(
        detector_name=RegexSemanticDetectorV2.NAME, classifications=tuple(classifications)
    )


class RegexSemanticDetectorV2:
    NAME = "regex"

    def detect(self, context_or_col, column_index: int = 0) -> DetectorResult:
        if hasattr(context_or_col, "get_column"):
            col = context_or_col.get_column(column_index)
        else:
            col = context_or_col
        vals = tuple(v.cleaned_value for v in col.values)
        return _evaluate_regex_values(vals)


def _evaluate_dictionary_name(raw_name: str) -> DetectorResult:
    raw = (raw_name or "").strip()
    if not raw:
        return DetectorResult(detector_name=DictionarySemanticDetectorV2.NAME, classifications=())

    raw_lower = raw.lower()
    raw_normalized = raw.replace(" ", "").replace("_", "").replace("-", "").lower()

    classifications = []
    for sem_name, _ in SEMANTIC_DICTIONARY:
        if raw_lower in _ALIAS_LOWER.get(sem_name, set()):
            conf = 0.95
            matched_alias = _ALIAS_TO_CANONICAL.get(raw_lower, raw)
        elif raw_normalized in _ALIAS_NORMALIZED.get(sem_name, set()):
            conf = 0.90
            matched_alias = _ALIAS_TO_CANONICAL.get(raw_normalized, raw)
        else:
            continue

        ev = SemanticEvidence(
            source=DictionarySemanticDetectorV2.NAME,
            score=conf,
            description=f"matched alias '{matched_alias}' for '{sem_name}'",
        )
        classifications.append(
            SemanticClassification(
                semantic_type=SemanticType[sem_name],
                confidence=conf,
                evidence=(ev,),
                detector=DictionarySemanticDetectorV2.NAME,
            )
        )

    return DetectorResult(
        detector_name=DictionarySemanticDetectorV2.NAME, classifications=tuple(classifications)
    )


class DictionarySemanticDetectorV2:
    NAME = "dictionary"

    def detect(self, context_or_col, column_index: int = 0) -> DetectorResult:
        if hasattr(context_or_col, "get_column"):
            col = context_or_col.get_column(column_index)
        else:
            col = context_or_col
        return _evaluate_dictionary_name(col.column_name)


class NativeColumnEvaluator:
    def evaluate(self, col: ColumnFeatureContext) -> tuple[DetectorResult, ...]:
        results = []

        # Order detectors to match v1 pipeline ordering used in tests: regex, dictionary, value_sampling
        regex_result = _evaluate_regex_values(tuple(v.cleaned_value for v in col.values))
        if regex_result and getattr(regex_result, "classifications", ()):
            results.append(regex_result)

        dictionary_result = _evaluate_dictionary_name(col.column_name)
        if dictionary_result and getattr(dictionary_result, "classifications", ()):
            results.append(dictionary_result)

        value_sampling_result = ValueSamplingDetectorV2().detect(col)
        if value_sampling_result and getattr(value_sampling_result, "classifications", ()):
            results.append(value_sampling_result)

        return tuple(results)


__all__ = [
    "ValueSamplingDetectorV2",
    "RegexSemanticDetectorV2",
    "DictionarySemanticDetectorV2",
    "NativeColumnEvaluator",
]
