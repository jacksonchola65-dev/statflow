from dataclasses import dataclass, field
from typing import Tuple, Optional
import math

from .semantic_types import DatasetDomain, SemanticType


@dataclass(frozen=True)
class DomainEvidence:
    domain: DatasetDomain
    semantic_type: SemanticType
    weight: float
    description: Optional[str] = None

    def __post_init__(self):
        if not isinstance(self.weight, (int, float)):
            raise TypeError("weight must be numeric")
        w = float(self.weight)
        if not math.isfinite(w) or w <= 0.0:
            raise ValueError("weight must be finite and greater than 0")


@dataclass(frozen=True)
class DomainScore:
    domain: DatasetDomain
    score: float
    evidence: Tuple[DomainEvidence, ...] = field(default_factory=tuple)

    def __post_init__(self):
        if not isinstance(self.score, (int, float)):
            raise TypeError("score must be numeric")
        s = float(self.score)
        if not math.isfinite(s) or s < 0.0 or s > 1.0:
            raise ValueError("score must be finite within [0.0, 1.0]")
        object.__setattr__(self, "evidence", tuple(self.evidence))


@dataclass(frozen=True)
class DomainPrediction:
    primary_domain: DatasetDomain
    confidence: float
    alternatives: Tuple[DomainScore, ...] = field(default_factory=tuple)
    evidence: Tuple[DomainEvidence, ...] = field(default_factory=tuple)

    def __post_init__(self):
        if not isinstance(self.confidence, (int, float)):
            raise TypeError("confidence must be numeric")
        c = float(self.confidence)
        if not math.isfinite(c) or c < 0.0 or c > 1.0:
            raise ValueError("confidence must be finite within [0.0, 1.0]")

        # Ensure alternatives is a tuple and sorted by descending score then domain value
        alts = tuple(self.alternatives)
        # Filter out any alternative equal to primary_domain
        filtered = [a for a in alts if a.domain != self.primary_domain]
        # sort by descending score, then domain name
        filtered.sort(key=lambda a: (-float(a.score), a.domain.value))
        object.__setattr__(self, "alternatives", tuple(filtered))

        # Ensure evidence is tuple and preserve ordering
        object.__setattr__(self, "evidence", tuple(self.evidence))
