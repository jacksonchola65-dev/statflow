import math
from dataclasses import dataclass, field
from typing import Iterable, Tuple

from .semantic_models import SemanticEvidence
from .semantic_types import SemanticType


def _trim_str(s: str) -> str:
    if not isinstance(s, str):
        raise TypeError("string expected")
    return s.strip()


def _finite_ratio(v: float, name: str) -> float:
    if not isinstance(v, (int, float)):
        raise TypeError(f"{name} must be numeric")
    f = float(v)
    if not math.isfinite(f):
        raise ValueError(f"{name} must be finite")
    if f < 0.0 or f > 1.0:
        raise ValueError(f"{name} must be within [0.0, 1.0]")
    return f


@dataclass(frozen=True)
class EntityCandidate:
    name: str
    semantic_types: Tuple[SemanticType, ...] = field(default_factory=tuple)
    source_columns: Tuple[str, ...] = field(default_factory=tuple)
    confidence: float = 0.0
    evidence: Tuple[SemanticEvidence, ...] = field(default_factory=tuple)

    def __post_init__(self):
        # name
        name = _trim_str(self.name)
        if not name:
            raise ValueError("name must be a non-empty string")
        object.__setattr__(self, "name", name)

        # semantic_types: preserve order, remove duplicates
        if not isinstance(self.semantic_types, Iterable):
            raise TypeError("semantic_types must be iterable of SemanticType")
        seen = []
        for t in self.semantic_types:
            if not isinstance(t, SemanticType):
                raise TypeError("semantic_types must contain SemanticType entries")
            if t not in seen:
                seen.append(t)
        object.__setattr__(self, "semantic_types", tuple(seen))

        # source_columns: trim, non-empty, unique preserve order
        if not isinstance(self.source_columns, Iterable):
            raise TypeError("source_columns must be iterable of strings")
        cols = []
        for c in self.source_columns:
            if not isinstance(c, str):
                raise TypeError("source_columns must contain strings")
            tc = c.strip()
            if not tc:
                raise ValueError("source column names must be non-empty after trimming")
            if tc not in cols:
                cols.append(tc)
        object.__setattr__(self, "source_columns", tuple(cols))

        # confidence
        if not isinstance(self.confidence, (int, float)):
            raise TypeError("confidence must be numeric")
        c = float(self.confidence)
        if not math.isfinite(c) or c < 0.0 or c > 1.0:
            raise ValueError("confidence must be finite within [0.0, 1.0]")
        object.__setattr__(self, "confidence", c)

        # evidence
        ev = tuple(self.evidence)
        for e in ev:
            if not isinstance(e, SemanticEvidence):
                raise TypeError("evidence must contain SemanticEvidence instances")
        object.__setattr__(self, "evidence", ev)


@dataclass(frozen=True)
class EntityKeyCandidate:
    entity_name: str
    column_name: str
    semantic_type: SemanticType
    confidence: float
    uniqueness_ratio: float
    null_ratio: float
    evidence: Tuple[SemanticEvidence, ...] = field(default_factory=tuple)

    def __post_init__(self):
        en = _trim_str(self.entity_name)
        if not en:
            raise ValueError("entity_name must be non-empty")
        object.__setattr__(self, "entity_name", en)

        cn = _trim_str(self.column_name)
        if not cn:
            raise ValueError("column_name must be non-empty")
        object.__setattr__(self, "column_name", cn)

        if not isinstance(self.semantic_type, SemanticType):
            raise TypeError("semantic_type must be a SemanticType")

        if not isinstance(self.confidence, (int, float)):
            raise TypeError("confidence must be numeric")
        c = float(self.confidence)
        if not math.isfinite(c) or c < 0.0 or c > 1.0:
            raise ValueError("confidence must be finite within [0.0,1.0]")
        object.__setattr__(self, "confidence", c)

        ur = _finite_ratio(self.uniqueness_ratio, "uniqueness_ratio")
        nr = _finite_ratio(self.null_ratio, "null_ratio")
        object.__setattr__(self, "uniqueness_ratio", ur)
        object.__setattr__(self, "null_ratio", nr)

        ev = tuple(self.evidence)
        for e in ev:
            if not isinstance(e, SemanticEvidence):
                raise TypeError("evidence must contain SemanticEvidence instances")
        object.__setattr__(self, "evidence", ev)


@dataclass(frozen=True)
class RelationshipCandidate:
    source_entity: str
    target_entity: str
    source_column: str
    target_column: str
    confidence: float
    relationship_type: str
    evidence: Tuple[SemanticEvidence, ...] = field(default_factory=tuple)

    def __post_init__(self):
        se = _trim_str(self.source_entity)
        if not se:
            raise ValueError("source_entity must be non-empty")
        object.__setattr__(self, "source_entity", se)

        te = _trim_str(self.target_entity)
        if not te:
            raise ValueError("target_entity must be non-empty")
        object.__setattr__(self, "target_entity", te)

        sc = _trim_str(self.source_column)
        if not sc:
            raise ValueError("source_column must be non-empty")
        object.__setattr__(self, "source_column", sc)

        tc = _trim_str(self.target_column)
        if not tc:
            raise ValueError("target_column must be non-empty")
        object.__setattr__(self, "target_column", tc)

        if not isinstance(self.relationship_type, str):
            raise TypeError("relationship_type must be a string")
        rt = self.relationship_type.strip()
        if not rt:
            raise ValueError("relationship_type must be non-empty")
        object.__setattr__(self, "relationship_type", rt)

        if not isinstance(self.confidence, (int, float)):
            raise TypeError("confidence must be numeric")
        c = float(self.confidence)
        if not math.isfinite(c) or c < 0.0 or c > 1.0:
            raise ValueError("confidence must be finite within [0.0,1.0]")
        object.__setattr__(self, "confidence", c)

        ev = tuple(self.evidence)
        for e in ev:
            if not isinstance(e, SemanticEvidence):
                raise TypeError("evidence must contain SemanticEvidence instances")
        object.__setattr__(self, "evidence", ev)
