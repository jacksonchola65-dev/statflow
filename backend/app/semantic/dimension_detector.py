from dataclasses import dataclass, field
from typing import Tuple, Sequence, Iterable
import math

from .analytics_role_models import DimensionCandidate, DimensionType
from .semantic_models import SemanticClassification, SemanticEvidence
from .semantic_types import SemanticType


_DIMENSION_TYPE_MAP = {
    SemanticType.DATE: DimensionType.TEMPORAL,
    SemanticType.DATETIME: DimensionType.TEMPORAL,
    SemanticType.YEAR: DimensionType.TEMPORAL,
    SemanticType.COUNTRY: DimensionType.GEOGRAPHIC,
    SemanticType.CITY: DimensionType.GEOGRAPHIC,
    SemanticType.PROVINCE: DimensionType.GEOGRAPHIC,
    SemanticType.DISTRICT: DimensionType.GEOGRAPHIC,
    SemanticType.PERSON: DimensionType.ENTITY,
    SemanticType.ORGANIZATION: DimensionType.ENTITY,
    SemanticType.IDENTIFIER: DimensionType.IDENTIFIER,
    SemanticType.BOOLEAN: DimensionType.BOOLEAN,
    SemanticType.CATEGORY: DimensionType.CATEGORICAL,
    SemanticType.TEXT: DimensionType.TEXTUAL,
}

_IGNORED_TYPES = {
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
    ratio = float(value)
    if not math.isfinite(ratio):
        raise ValueError(f"{name} must be finite")
    if ratio < 0.0 or ratio > 1.0:
        raise ValueError(f"{name} must be within [0.0, 1.0]")
    return ratio


@dataclass(frozen=True)
class DimensionColumnInput:
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

        object.__setattr__(self, "cardinality_ratio", _finite_ratio(self.cardinality_ratio, "cardinality_ratio"))
        object.__setattr__(self, "null_ratio", _finite_ratio(self.null_ratio, "null_ratio"))


class DimensionDetector:
    @staticmethod
    def discover(columns: Sequence[DimensionColumnInput]) -> Tuple[DimensionCandidate, ...]:
        if not isinstance(columns, Sequence):
            raise TypeError("columns must be a sequence of DimensionColumnInput")

        seen_names = set()
        candidates = []

        for col in columns:
            if not isinstance(col, DimensionColumnInput):
                raise TypeError("columns must contain DimensionColumnInput instances")

            name = col.column_name
            if name in seen_names:
                continue
            seen_names.add(name)

            if col.null_ratio > 0.50:
                continue

            eligible = [
                c for c in col.classifications
                if isinstance(c, SemanticClassification)
                and c.semantic_type not in _IGNORED_TYPES
                and c.semantic_type in _DIMENSION_TYPE_MAP
                and float(c.confidence) >= 0.60
            ]
            if not eligible:
                continue

            eligible.sort(key=lambda c: (-float(c.confidence), c.semantic_type.value))
            selected = eligible[0]

            if selected.semantic_type == SemanticType.TEXT and col.cardinality_ratio > 0.50:
                continue

            dimension_type = _DIMENSION_TYPE_MAP[selected.semantic_type]
            candidate = DimensionCandidate(
                name=name,
                semantic_type=selected.semantic_type,
                dimension_type=dimension_type,
                confidence=float(selected.confidence),
                cardinality_ratio=col.cardinality_ratio,
                null_ratio=col.null_ratio,
                evidence=tuple(selected.evidence),
            )
            candidates.append(candidate)

        candidates.sort(key=lambda d: (-float(d.confidence), d.name))
        return tuple(candidates)
