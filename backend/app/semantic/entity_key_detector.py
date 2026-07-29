from dataclasses import dataclass, field
from typing import Sequence, Tuple, Iterable, List
import math

from .semantic_models import SemanticClassification, SemanticEvidence
from .semantic_types import SemanticType
from .entity_models import EntityCandidate, EntityKeyCandidate


KEY_TYPES = {SemanticType.IDENTIFIER, SemanticType.INTEGER, SemanticType.TEXT}

_SUFFIXES = {"id", "identifier", "code", "key"}


def _normalize_name(s: str) -> str:
    if not isinstance(s, str):
        raise TypeError("string expected")
    t = s.strip()
    t = t.replace("_", " ").replace("-", " ")
    t = " ".join(t.split())
    return t.lower()


def _normalize_column_and_strip_suffix(s: str) -> str:
    norm = _normalize_name(s)
    parts = norm.split()
    if parts and parts[-1] in _SUFFIXES:
        new = " ".join(parts[:-1]).strip()
        if new:
            return new
    return norm


@dataclass(frozen=True)
class EntityKeyColumnInput:
    column_name: str
    classifications: Tuple[SemanticClassification, ...] = field(default_factory=tuple)
    uniqueness_ratio: float = 0.0
    null_ratio: float = 0.0

    def __post_init__(self):
        if not isinstance(self.column_name, str):
            raise TypeError("column_name must be a string")
        cn = self.column_name.strip()
        if not cn:
            raise ValueError("column_name must be non-empty")
        object.__setattr__(self, "column_name", cn)

        if not isinstance(self.classifications, Iterable):
            raise TypeError("classifications must be iterable")
        cls = tuple(self.classifications)
        for c in cls:
            if not isinstance(c, SemanticClassification):
                raise TypeError("classifications must contain SemanticClassification instances")
        object.__setattr__(self, "classifications", cls)

        if not isinstance(self.uniqueness_ratio, (int, float)):
            raise TypeError("uniqueness_ratio must be numeric")
        ur = float(self.uniqueness_ratio)
        if not math.isfinite(ur) or ur < 0.0 or ur > 1.0:
            raise ValueError("uniqueness_ratio must be within [0.0,1.0]")
        object.__setattr__(self, "uniqueness_ratio", ur)

        if not isinstance(self.null_ratio, (int, float)):
            raise TypeError("null_ratio must be numeric")
        nr = float(self.null_ratio)
        if not math.isfinite(nr) or nr < 0.0 or nr > 1.0:
            raise ValueError("null_ratio must be within [0.0,1.0]")
        object.__setattr__(self, "null_ratio", nr)


@dataclass(frozen=True)
class EntityKeyDetectionInput:
    entities: Tuple[EntityCandidate, ...] = field(default_factory=tuple)
    columns: Tuple[EntityKeyColumnInput, ...] = field(default_factory=tuple)

    def __post_init__(self):
        if not isinstance(self.entities, Iterable):
            raise TypeError("entities must be iterable")
        ent = tuple(self.entities)
        for e in ent:
            if not isinstance(e, EntityCandidate):
                raise TypeError("entities must contain EntityCandidate instances")
        object.__setattr__(self, "entities", ent)

        if not isinstance(self.columns, Iterable):
            raise TypeError("columns must be iterable")
        cols = tuple(self.columns)
        for c in cols:
            if not isinstance(c, EntityKeyColumnInput):
                raise TypeError("columns must contain EntityKeyColumnInput instances")
        object.__setattr__(self, "columns", cols)


class EntityKeyDetector:
    @staticmethod
    def discover(input_data: EntityKeyDetectionInput) -> Tuple[EntityKeyCandidate, ...]:
        if not isinstance(input_data, EntityKeyDetectionInput):
            raise TypeError("input_data must be EntityKeyDetectionInput")

        entities = list(input_data.entities)
        cols = list(input_data.columns)

        if len(entities) == 0 or len(cols) == 0:
            return tuple()

        # Build normalized entity name map preserving first-seen order
        norm_to_entity_index = {}
        norm_entities = []
        for idx, e in enumerate(entities):
            if not isinstance(e, EntityCandidate):
                raise TypeError("entities must contain EntityCandidate instances")
            n = _normalize_name(e.name)
            norm_entities.append(n)
            if n not in norm_to_entity_index:
                norm_to_entity_index[n] = idx

        candidates: List[EntityKeyCandidate] = []

        for col in cols:
            if not isinstance(col, EntityKeyColumnInput):
                raise TypeError("columns must contain EntityKeyColumnInput instances")

            # select highest-confidence eligible classification among KEY_TYPES
            eligible = [c for c in col.classifications if c.semantic_type in KEY_TYPES]
            if not eligible:
                continue
            # sort by confidence desc, then semantic_type.value for tie-break
            eligible_sorted = sorted(eligible, key=lambda c: (-float(c.confidence), c.semantic_type.value))
            top = eligible_sorted[0]
            if float(top.confidence) < 0.60:
                continue

            # check thresholds based on type
            ur = float(col.uniqueness_ratio)
            nr = float(col.null_ratio)

            if top.semantic_type == SemanticType.IDENTIFIER:
                if ur < 0.80 or nr > 0.20:
                    continue
                base = 0.50 * float(top.confidence) + 0.35 * ur + 0.15 * (1.0 - nr)
            else:
                # INTEGER or TEXT
                if ur < 0.95 or nr > 0.05:
                    continue
                base = 0.35 * float(top.confidence) + 0.50 * ur + 0.15 * (1.0 - nr)

            # clamp to 0.0 - 0.99
            conf = max(0.0, min(0.99, float(base)))

            # match entity by normalized names (strip suffixes from column)
            norm_col = _normalize_column_and_strip_suffix(col.column_name)
            if norm_col not in norm_to_entity_index:
                continue
            ent_idx = norm_to_entity_index[norm_col]
            ent = entities[ent_idx]

            ek = EntityKeyCandidate(
                entity_name=ent.name,
                column_name=col.column_name,
                semantic_type=top.semantic_type,
                confidence=conf,
                uniqueness_ratio=ur,
                null_ratio=nr,
                evidence=tuple(top.evidence),
            )
            candidates.append(ek)

        # sort by descending confidence, entity_name CI, column_name CI, semantic_type.value
        candidates.sort(key=lambda k: (-float(k.confidence), k.entity_name.lower(), k.column_name.lower(), k.semantic_type.value))

        return tuple(candidates)
