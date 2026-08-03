import math
from dataclasses import dataclass, field
from typing import Iterable, Sequence, Tuple

from .analytics_role_models import Aggregation, MeasureCandidate
from .semantic_models import SemanticClassification
from .semantic_types import SemanticType

_MEASURE_TYPES = {
    SemanticType.INTEGER,
    SemanticType.DECIMAL,
    SemanticType.CURRENCY,
    SemanticType.PERCENTAGE,
    SemanticType.QUANTITY,
}


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
        raise TypeError(f"{name} must be numeric")
    pct = float(value)
    if not math.isfinite(pct):
        raise ValueError(f"{name} must be finite")
    if pct < 0.0 or pct > 1.0:
        raise ValueError(f"{name} must be within [0.0, 1.0]")
    return pct


def _aggregation_for_type(semantic_type: SemanticType) -> Aggregation:
    if semantic_type in {
        SemanticType.CURRENCY,
        SemanticType.QUANTITY,
        SemanticType.INTEGER,
        SemanticType.DECIMAL,
    }:
        return Aggregation.SUM
    if semantic_type == SemanticType.PERCENTAGE:
        return Aggregation.AVG
    raise ValueError("Unsupported measure semantic type")


@dataclass(frozen=True)
class MeasureColumnInput:
    column_name: str
    classifications: Tuple[SemanticClassification, ...] = field(default_factory=tuple)
    cardinality_ratio: float = 0.0
    null_ratio: float = 0.0

    def __post_init__(self):
        object.__setattr__(self, "column_name", _trim_str(self.column_name, "column_name"))

        if not isinstance(self.classifications, Iterable):
            raise TypeError("classifications must be iterable")
        cls = tuple(self.classifications)
        for c in cls:
            if not isinstance(c, SemanticClassification):
                raise TypeError("classifications must contain SemanticClassification instances")
        object.__setattr__(self, "classifications", cls)

        object.__setattr__(
            self, "cardinality_ratio", _finite_ratio(self.cardinality_ratio, "cardinality_ratio")
        )
        object.__setattr__(self, "null_ratio", _finite_ratio(self.null_ratio, "null_ratio"))


class MeasureDetector:
    @staticmethod
    def discover(columns: Sequence[MeasureColumnInput]) -> Tuple[MeasureCandidate, ...]:
        if not isinstance(columns, Sequence):
            raise TypeError("columns must be a sequence of MeasureColumnInput")

        seen_names = set()
        candidates = []

        for col in columns:
            if not isinstance(col, MeasureColumnInput):
                raise TypeError("columns must contain MeasureColumnInput instances")

            name = col.column_name
            if name in seen_names:
                continue
            seen_names.add(name)

            eligible = [
                c
                for c in col.classifications
                if isinstance(c, SemanticClassification) and c.semantic_type in _MEASURE_TYPES
            ]
            if not eligible:
                continue

            top = max(eligible, key=lambda c: float(c.confidence))
            conf = float(top.confidence)
            if conf < 0.60:
                continue

            aggregation = _aggregation_for_type(top.semantic_type)
            candidate = MeasureCandidate(
                name=name,
                semantic_type=top.semantic_type,
                aggregation=aggregation,
                confidence=conf,
                cardinality_ratio=col.cardinality_ratio,
                null_ratio=col.null_ratio,
                evidence=tuple(top.evidence),
            )
            candidates.append(candidate)

        candidates.sort(key=lambda m: (-float(m.confidence), m.name))
        return tuple(candidates)
