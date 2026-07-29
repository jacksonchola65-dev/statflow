from dataclasses import dataclass, field
from typing import Tuple, Optional, Dict
from uuid import UUID, uuid4

from .semantic_types import DatasetDomain, SemanticType, ColumnRole
import math


@dataclass(frozen=True)
class SemanticColumn:
    name: str
    semantic_type: SemanticType = SemanticType.UNKNOWN
    role: ColumnRole = ColumnRole.UNKNOWN
    confidence: float = 0.0
    metadata: Dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class SemanticEntity:
    id: UUID
    name: str
    semantic_type: SemanticType = SemanticType.UNKNOWN
    columns: Tuple[SemanticColumn, ...] = field(default_factory=tuple)
    confidence: float = 0.0
    metadata: Dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class SemanticRelationship:
    source_entity_id: UUID
    target_entity_id: UUID
    relationship_type: str
    confidence: float = 0.0
    properties: Dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class SemanticProfile:
    dataset_domain: DatasetDomain = DatasetDomain.UNKNOWN
    columns: Tuple[SemanticColumn, ...] = field(default_factory=tuple)
    entities: Tuple[SemanticEntity, ...] = field(default_factory=tuple)
    relationships: Tuple[SemanticRelationship, ...] = field(default_factory=tuple)
    overall_confidence: float = 0.0
    metadata: Dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class SemanticEvidence:
    source: str
    score: float
    description: Optional[str] = None

    def __post_init__(self):
        if not isinstance(self.score, (float, int)):
            raise TypeError("score must be a float")
        s = float(self.score)
        if not math.isfinite(s):
            raise ValueError("score must be finite and not NaN")


@dataclass(frozen=True)
class SemanticSuggestion:
    semantic_type: SemanticType
    confidence: float

    def __post_init__(self):
        if not isinstance(self.confidence, (float, int)):
            raise TypeError("confidence must be a float")
        c = float(self.confidence)
        if not math.isfinite(c):
            raise ValueError("confidence must be finite and not NaN")
        if c < 0.0 or c > 1.0:
            raise ValueError("confidence must be between 0.0 and 1.0")


@dataclass(frozen=True)
class SemanticClassification:
    semantic_type: SemanticType
    confidence: float
    evidence: Tuple[SemanticEvidence, ...] = field(default_factory=tuple)
    detector: Optional[str] = None
    suggestions: Tuple[SemanticSuggestion, ...] = field(default_factory=tuple)

    def __post_init__(self):
        if not isinstance(self.confidence, (float, int)):
            raise TypeError("confidence must be a float")
        c = float(self.confidence)
        if not math.isfinite(c):
            raise ValueError("confidence must be finite and not NaN")
        if c < 0.0 or c > 1.0:
            raise ValueError("confidence must be between 0.0 and 1.0")

        # Ensure evidence is an immutable tuple and preserve order
        ev = tuple(self.evidence)
        object.__setattr__(self, "evidence", ev)

        # Ensure suggestions are ordered by confidence descending
        sug = tuple(sorted(self.suggestions, key=lambda s: float(s.confidence), reverse=True))
        object.__setattr__(self, "suggestions", sug)
