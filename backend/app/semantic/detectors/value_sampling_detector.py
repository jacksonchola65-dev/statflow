from statistics import median, pvariance
from typing import List

from app.semantic.detectors.base import DetectorInput, DetectorResult, SemanticDetector
from app.semantic.semantic_models import SemanticClassification, SemanticEvidence
from app.semantic.semantic_types import SemanticType


class ValueSamplingDetector(SemanticDetector):
    NAME = "value_sampling"

    def detect(self, input: DetectorInput) -> DetectorResult:
        return self.detect_batch([input])[0]

    def detect_batch(self, inputs: list[DetectorInput]) -> list[DetectorResult]:
        results: list[DetectorResult] = []
        for input_obj in inputs:
            if not input_obj.values:
                results.append(DetectorResult(detector_name=self.NAME, classifications=()))
                continue

            strs = [v if isinstance(v, str) else str(v) for v in input_obj.values]
            sample_size = len(strs)
            if sample_size == 0:
                results.append(DetectorResult(detector_name=self.NAME, classifications=()))
                continue

            # Boolean detection tokens
            bool_tokens = {"true", "false", "yes", "no", "y", "n", "0", "1"}
            lowered = [s.strip().lower() for s in strs]

            # BOOLEAN: all values in tokens
            if all(s in bool_tokens for s in lowered):
                ev = SemanticEvidence(
                    source=self.NAME,
                    score=0.95,
                    description=f"sample_size={sample_size}; all values boolean-like",
                )
                results.append(
                    DetectorResult(
                        detector_name=self.NAME,
                        classifications=(
                            SemanticClassification(
                                semantic_type=SemanticType.BOOLEAN,
                                confidence=0.95,
                                evidence=(ev,),
                                detector=self.NAME,
                            ),
                        ),
                    )
                )
                continue

            # Numeric checks
            numeric_values: List[float] = []
            int_count = 0
            decimal_count = 0
            for s in strs:
                try:
                    if "." in s or "e" in s.lower():
                        f = float(s)
                        numeric_values.append(f)
                        if not float(f).is_integer():
                            decimal_count += 1
                        else:
                            int_count += 1
                    else:
                        i = int(s)
                        numeric_values.append(float(i))
                        int_count += 1
                except Exception:
                    continue

            numeric_count = len(numeric_values)
            classifications = []

            # DECIMAL: majority of numeric values have decimals
            if numeric_count > 0 and decimal_count / numeric_count > 0.5:
                ev = SemanticEvidence(
                    source=self.NAME,
                    score=0.95,
                    description=f"sample_size={sample_size}; numeric_count={numeric_count}; decimal_ratio={decimal_count / numeric_count:.2f}",
                )
                classifications.append(
                    SemanticClassification(
                        semantic_type=SemanticType.DECIMAL,
                        confidence=0.95,
                        evidence=(ev,),
                        detector=self.NAME,
                    )
                )
                results.append(
                    DetectorResult(detector_name=self.NAME, classifications=tuple(classifications))
                )
                continue

            # AGE detection: numeric and 95% within 0-130; require reasonable sample size
            if numeric_count > 0 and sample_size >= 10:
                within_age = sum(1 for x in numeric_values if 0 <= x <= 130)
                if within_age / numeric_count >= 0.95:
                    ev = SemanticEvidence(
                        source=self.NAME,
                        score=0.95,
                        description=f"sample_size={sample_size}; numeric_count={numeric_count}; within_age_ratio={within_age / numeric_count:.2f}",
                    )
                    classifications.append(
                        SemanticClassification(
                            semantic_type=SemanticType.AGE,
                            confidence=0.95,
                            evidence=(ev,),
                            detector=self.NAME,
                        )
                    )
                    results.append(
                        DetectorResult(
                            detector_name=self.NAME, classifications=tuple(classifications)
                        )
                    )
                    continue

            # PERCENTAGE detection: numeric and values in 0-100 or 0-1
            if numeric_count > 0:
                in_0_100 = sum(1 for x in numeric_values if 0 <= x <= 100)
                in_0_1 = sum(1 for x in numeric_values if 0.0 <= x <= 1.0)
                med_val = median(numeric_values) if numeric_values else 0
                if (
                    in_0_100 / numeric_count >= 0.9 or in_0_1 / numeric_count >= 0.9
                ) and med_val >= 10:
                    ev = SemanticEvidence(
                        source=self.NAME,
                        score=0.95,
                        description=f"sample_size={sample_size}; numeric_count={numeric_count}; in0_100={in_0_100}; in0_1={in_0_1}",
                    )
                    classifications.append(
                        SemanticClassification(
                            semantic_type=SemanticType.PERCENTAGE,
                            confidence=0.95,
                            evidence=(ev,),
                            detector=self.NAME,
                        )
                    )
                    results.append(
                        DetectorResult(
                            detector_name=self.NAME, classifications=tuple(classifications)
                        )
                    )
                    continue

            # CURRENCY detection: numeric only, median > 100 and variance reasonably high
            if numeric_count == sample_size and numeric_count > 0:
                med = median(numeric_values)
                var = pvariance(numeric_values)
                if med > 100 and var > 1000:
                    ev = SemanticEvidence(
                        source=self.NAME,
                        score=0.95,
                        description=f"sample_size={sample_size}; median={med:.2f}; variance={var:.2f}",
                    )
                    classifications.append(
                        SemanticClassification(
                            semantic_type=SemanticType.CURRENCY,
                            confidence=0.95,
                            evidence=(ev,),
                            detector=self.NAME,
                        )
                    )
                    results.append(
                        DetectorResult(
                            detector_name=self.NAME, classifications=tuple(classifications)
                        )
                    )
                    continue

            # INTEGER: all sampled values are numeric and integer
            if numeric_count == sample_size and int_count == numeric_count:
                ev = SemanticEvidence(
                    source=self.NAME,
                    score=0.95,
                    description=f"sample_size={sample_size}; numeric_count={numeric_count}; all integer",
                )
                classifications.append(
                    SemanticClassification(
                        semantic_type=SemanticType.INTEGER,
                        confidence=0.95,
                        evidence=(ev,),
                        detector=self.NAME,
                    )
                )
                results.append(
                    DetectorResult(detector_name=self.NAME, classifications=tuple(classifications))
                )
                continue

            # QUANTITY: positive numeric values
            if numeric_count == sample_size and all(x >= 0 for x in numeric_values):
                ev = SemanticEvidence(
                    source=self.NAME,
                    score=0.9,
                    description=f"sample_size={sample_size}; numeric_count={numeric_count}; min={min(numeric_values):.2f}; max={max(numeric_values):.2f}",
                )
                classifications.append(
                    SemanticClassification(
                        semantic_type=SemanticType.QUANTITY,
                        confidence=0.9,
                        evidence=(ev,),
                        detector=self.NAME,
                    )
                )
                results.append(
                    DetectorResult(detector_name=self.NAME, classifications=tuple(classifications))
                )
                continue

            # CATEGORY: unique ratio <= 0.20 and minimum sample size 20
            unique_count = len(set(strs))
            unique_ratio = unique_count / sample_size
            if sample_size >= 20 and unique_ratio <= 0.20:
                ev = SemanticEvidence(
                    source=self.NAME,
                    score=0.95,
                    description=f"sample_size={sample_size}; unique_count={unique_count}; unique_ratio={unique_ratio:.2f}",
                )
                classifications.append(
                    SemanticClassification(
                        semantic_type=SemanticType.CATEGORY,
                        confidence=0.95,
                        evidence=(ev,),
                        detector=self.NAME,
                    )
                )
                results.append(
                    DetectorResult(detector_name=self.NAME, classifications=tuple(classifications))
                )
                continue

            # TEXT fallback
            ev = SemanticEvidence(
                source=self.NAME,
                score=0.5,
                description=f"sample_size={sample_size}; unique_count={unique_count if 'unique_count' in locals() else len(set(strs))}",
            )
            classifications.append(
                SemanticClassification(
                    semantic_type=SemanticType.TEXT,
                    confidence=0.5,
                    evidence=(ev,),
                    detector=self.NAME,
                )
            )
            results.append(
                DetectorResult(detector_name=self.NAME, classifications=tuple(classifications))
            )

        return results
