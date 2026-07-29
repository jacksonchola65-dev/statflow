from typing import Sequence, Tuple, List
from collections import namedtuple

from .domain_models import DomainScore, DomainPrediction
from .semantic_types import DatasetDomain


class DatasetDomainDetector:
    @staticmethod
    def predict(scores: Sequence[DomainScore]) -> DomainPrediction:
        # Validate input
        if not isinstance(scores, Sequence):
            raise TypeError("scores must be a sequence of DomainScore")
        for s in scores:
            if not isinstance(s, DomainScore):
                raise TypeError("all items must be DomainScore instances")

        if len(scores) == 0:
            return DomainPrediction(primary_domain=DatasetDomain.CUSTOM, confidence=0.0, alternatives=(), evidence=())

        # Ignore non-positive scores
        positive = [s for s in scores if float(s.score) > 0.0]

        if not positive:
            return DomainPrediction(primary_domain=DatasetDomain.CUSTOM, confidence=0.0, alternatives=(), evidence=())

        # Sort deterministically by descending score then domain value
        positive_sorted = sorted(positive, key=lambda d: (-float(d.score), d.domain.value))

        top = positive_sorted[0]
        second = positive_sorted[1] if len(positive_sorted) > 1 else None

        # Determine ambiguity and minimum confidence
        ambiguous = False
        if second is not None:
            if (float(top.score) - float(second.score)) < 0.10:
                ambiguous = True

        low_confidence = float(top.score) < 0.25

        # Build alternatives: remaining positive scores excluding primary, limited to top 3
        alternatives_candidates = [d for d in positive_sorted if d.domain != top.domain]
        alternatives_limited = tuple(alternatives_candidates[:3])

        if ambiguous or low_confidence:
            # Return CUSTOM with highest score as confidence, alternatives include top positives limited to 3
            alts = tuple(positive_sorted[:3])
            return DomainPrediction(primary_domain=DatasetDomain.CUSTOM, confidence=float(top.score), alternatives=alts, evidence=tuple(top.evidence))

        # Normal case: primary is top domain
        return DomainPrediction(primary_domain=top.domain, confidence=float(top.score), alternatives=alternatives_limited, evidence=tuple(top.evidence))
