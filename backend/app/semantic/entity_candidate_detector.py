from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Sequence, Tuple

from .entity_models import EntityCandidate
from .semantic_models import SemanticClassification, SemanticEvidence
from .semantic_types import SemanticType

ENTITY_TYPES = {
    SemanticType.PERSON,
    SemanticType.ORGANIZATION,
    SemanticType.COUNTRY,
    SemanticType.CITY,
    SemanticType.PROVINCE,
    SemanticType.DISTRICT,
}

_SUFFIXES = {"id", "identifier", "name", "code", "key"}


def _normalize_column_name(name: str) -> str:
    s = name.strip()
    s = s.replace("_", " ").replace("-", " ")
    s = " ".join(s.split())
    return s


def _derive_candidate_name(col_name: str) -> str:
    norm = _normalize_column_name(col_name)
    parts = norm.split()
    if parts:
        last = parts[-1].lower()
        if last in _SUFFIXES:
            new = " ".join(parts[:-1]).strip()
            if new:
                return new
    return norm


@dataclass(frozen=True)
class EntityColumnInput:
    column_name: str
    classifications: Tuple[SemanticClassification, ...] = field(default_factory=tuple)

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
                raise TypeError("all classifications must be SemanticClassification instances")
            # ensure confidence valid by relying on SemanticClassification validation
        object.__setattr__(self, "classifications", cls)


class EntityCandidateDetector:
    @staticmethod
    def discover(columns: Sequence[EntityColumnInput]) -> Tuple[EntityCandidate, ...]:
        if not isinstance(columns, Iterable):
            raise TypeError("columns must be iterable of EntityColumnInput")

        cols = list(columns)
        if len(cols) == 0:
            return tuple()

        # Validate types
        for c in cols:
            if not isinstance(c, EntityColumnInput):
                raise TypeError("each item must be EntityColumnInput")

        # For each column, collect matching entity-bearing classifications (>=0.60)
        col_matches: List[List[SemanticClassification]] = []
        col_candidate_flag: List[bool] = []
        derived_names: List[str] = []
        for col in cols:
            matches: List[SemanticClassification] = []
            for cl in col.classifications:
                if cl.semantic_type in ENTITY_TYPES and float(cl.confidence) >= 0.60:
                    matches.append(cl)
            col_matches.append(matches)
            col_candidate_flag.append(len(matches) > 0)
            derived_names.append(_derive_candidate_name(col.column_name))

        # Group columns by derived name (case-insensitive)
        groups: Dict[str, Dict] = {}
        for idx, col in enumerate(cols):
            if not col_candidate_flag[idx]:
                continue
            key = derived_names[idx].lower()
            if key not in groups:
                groups[key] = {
                    "first_name": derived_names[idx],
                    "cols": [],
                    "types_order": [],
                    "evidence": [],
                    "max_conf": 0.0,
                }
            g = groups[key]
            # add source column (trimmed original) if not duplicate
            if col.column_name not in g["cols"]:
                g["cols"].append(col.column_name)
            # iterate classifications in original order
            for cl in col_matches[idx]:
                # semantic types
                if cl.semantic_type not in g["types_order"]:
                    g["types_order"].append(cl.semantic_type)
                # evidence: append classification evidence preserving order
                for ev in cl.evidence:
                    if not isinstance(ev, SemanticEvidence):
                        raise TypeError("evidence items must be SemanticEvidence")
                    g["evidence"].append(ev)
                # confidence
                if float(cl.confidence) > g["max_conf"]:
                    g["max_conf"] = float(cl.confidence)

        # Build EntityCandidate objects
        candidates: List[EntityCandidate] = []
        for key, g in groups.items():
            ec = EntityCandidate(
                name=g["first_name"],
                semantic_types=tuple(g["types_order"]),
                source_columns=tuple(g["cols"]),
                confidence=float(g["max_conf"]),
                evidence=tuple(g["evidence"]),
            )
            candidates.append(ec)

        # Sort final candidates by descending confidence, then normalized entity name, then first source column
        candidates.sort(
            key=lambda e: (
                -float(e.confidence),
                e.name.lower(),
                e.source_columns[0] if e.source_columns else "",
            )
        )

        return tuple(candidates)
