import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Tuple

from .semantic_models import SemanticEvidence
from .semantic_types import SemanticType


class Aggregation(str, Enum):
    SUM = "SUM"
    AVG = "AVG"
    MIN = "MIN"
    MAX = "MAX"
    COUNT = "COUNT"
    COUNT_DISTINCT = "COUNT_DISTINCT"
    NONE = "NONE"


class DimensionType(str, Enum):
    CATEGORICAL = "CATEGORICAL"
    TEMPORAL = "TEMPORAL"
    GEOGRAPHIC = "GEOGRAPHIC"
    ENTITY = "ENTITY"
    IDENTIFIER = "IDENTIFIER"
    BOOLEAN = "BOOLEAN"
    TEXTUAL = "TEXTUAL"


def _trim_str(value: str, name: str) -> str:
    if not isinstance(value, str):
        raise TypeError(f"{name} must be a string")
    trimmed = value.strip()
    if not trimmed:
        raise ValueError(f"{name} must be a non-empty string")
    return trimmed


def _finite_ratio(value: float, name: str) -> float:
    if isinstance(value, bool):
        raise TypeError(f"{name} must be a finite non-boolean number")
    if not isinstance(value, (int, float)):
        raise TypeError(f"{name} must be a finite number")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{name} must be finite")
    if result < 0.0 or result > 1.0:
        raise ValueError(f"{name} must be within [0.0, 1.0]")
    return result


def _validate_confidence(value: float) -> float:
    if isinstance(value, bool):
        raise TypeError("confidence must be a finite non-boolean number")
    if not isinstance(value, (int, float)):
        raise TypeError("confidence must be a finite number")
    score = float(value)
    if not math.isfinite(score):
        raise ValueError("confidence must be finite")
    if score < 0.0 or score > 1.0:
        raise ValueError("confidence must be within [0.0, 1.0]")
    return score


def _validate_enum(value, enum_cls, name: str):
    if isinstance(value, enum_cls):
        return value
    if isinstance(value, str):
        if value not in enum_cls.__members__:
            raise ValueError(f"{name} must be one of {[m for m in enum_cls.__members__]}")
        return enum_cls[value]
    raise TypeError(f"{name} must be a {enum_cls.__name__} or its uppercase name")


@dataclass(frozen=True)
class MeasureCandidate:
    name: str
    semantic_type: SemanticType
    aggregation: Aggregation
    confidence: float
    cardinality_ratio: float
    null_ratio: float
    evidence: Tuple[SemanticEvidence, ...] = field(default_factory=tuple)

    def __post_init__(self):
        object.__setattr__(self, "name", _trim_str(self.name, "name"))

        if not isinstance(self.semantic_type, SemanticType):
            raise TypeError("semantic_type must be a SemanticType")

        self_aggregation = _validate_enum(self.aggregation, Aggregation, "aggregation")
        object.__setattr__(self, "aggregation", self_aggregation)

        object.__setattr__(self, "confidence", _validate_confidence(self.confidence))
        object.__setattr__(
            self, "cardinality_ratio", _finite_ratio(self.cardinality_ratio, "cardinality_ratio")
        )
        object.__setattr__(self, "null_ratio", _finite_ratio(self.null_ratio, "null_ratio"))

        evidence_tuple = tuple(self.evidence)
        for e in evidence_tuple:
            if not isinstance(e, SemanticEvidence):
                raise TypeError("evidence must contain SemanticEvidence instances")
        object.__setattr__(self, "evidence", evidence_tuple)


@dataclass(frozen=True)
class DimensionCandidate:
    name: str
    semantic_type: SemanticType
    dimension_type: DimensionType
    confidence: float
    cardinality_ratio: float
    null_ratio: float
    evidence: Tuple[SemanticEvidence, ...] = field(default_factory=tuple)

    def __post_init__(self):
        object.__setattr__(self, "name", _trim_str(self.name, "name"))

        if not isinstance(self.semantic_type, SemanticType):
            raise TypeError("semantic_type must be a SemanticType")

        self_dimension = _validate_enum(self.dimension_type, DimensionType, "dimension_type")
        object.__setattr__(self, "dimension_type", self_dimension)

        object.__setattr__(self, "confidence", _validate_confidence(self.confidence))
        object.__setattr__(
            self, "cardinality_ratio", _finite_ratio(self.cardinality_ratio, "cardinality_ratio")
        )
        object.__setattr__(self, "null_ratio", _finite_ratio(self.null_ratio, "null_ratio"))

        evidence_tuple = tuple(self.evidence)
        for e in evidence_tuple:
            if not isinstance(e, SemanticEvidence):
                raise TypeError("evidence must contain SemanticEvidence instances")
        object.__setattr__(self, "evidence", evidence_tuple)


@dataclass(frozen=True)
class AnalyticsRoleProfile:
    measure_candidates: Tuple[MeasureCandidate, ...] = field(default_factory=tuple)
    dimension_candidates: Tuple[DimensionCandidate, ...] = field(default_factory=tuple)

    def __post_init__(self):
        measure_tuple = tuple(self.measure_candidates)
        for m in measure_tuple:
            if not isinstance(m, MeasureCandidate):
                raise TypeError("measure_candidates must contain MeasureCandidate instances")
        object.__setattr__(self, "measure_candidates", measure_tuple)

        dimension_tuple = tuple(self.dimension_candidates)
        for d in dimension_tuple:
            if not isinstance(d, DimensionCandidate):
                raise TypeError("dimension_candidates must contain DimensionCandidate instances")
        object.__setattr__(self, "dimension_candidates", dimension_tuple)
