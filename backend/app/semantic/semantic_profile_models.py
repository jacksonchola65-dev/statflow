from dataclasses import dataclass, field
from typing import Iterable, Tuple

from .analytics_role_models import AnalyticsRoleProfile, DimensionCandidate, MeasureCandidate
from .entity_models import EntityCandidate, EntityKeyCandidate, RelationshipCandidate
from .semantic_models import SemanticClassification, SemanticEntity, SemanticRelationship
from .semantic_types import DatasetDomain


def _tupleify(value, name: str):
    if not isinstance(value, Iterable):
        raise TypeError(f"{name} must be iterable")
    return tuple(value)


@dataclass(frozen=True)
class SemanticColumnProfile:
    column_name: str
    classifications: Tuple[SemanticClassification, ...] = field(default_factory=tuple)
    key_candidates: Tuple[EntityKeyCandidate, ...] = field(default_factory=tuple)
    measure_candidates: Tuple[MeasureCandidate, ...] = field(default_factory=tuple)
    dimension_candidates: Tuple[DimensionCandidate, ...] = field(default_factory=tuple)

    def __post_init__(self):
        if not isinstance(self.column_name, str):
            raise TypeError("column_name must be a string")
        if not self.column_name.strip():
            raise ValueError("column_name must be a non-empty string")
        object.__setattr__(self, "column_name", self.column_name.strip())

        classifications = _tupleify(self.classifications, "classifications")
        for c in classifications:
            if not isinstance(c, SemanticClassification):
                raise TypeError("classifications must contain SemanticClassification instances")
        object.__setattr__(self, "classifications", classifications)

        key_candidates = _tupleify(self.key_candidates, "key_candidates")
        for k in key_candidates:
            if not isinstance(k, EntityKeyCandidate):
                raise TypeError("key_candidates must contain EntityKeyCandidate instances")
        object.__setattr__(self, "key_candidates", key_candidates)

        measure_candidates = _tupleify(self.measure_candidates, "measure_candidates")
        for m in measure_candidates:
            if not isinstance(m, MeasureCandidate):
                raise TypeError("measure_candidates must contain MeasureCandidate instances")
        object.__setattr__(self, "measure_candidates", measure_candidates)

        dimension_candidates = _tupleify(self.dimension_candidates, "dimension_candidates")
        for d in dimension_candidates:
            if not isinstance(d, DimensionCandidate):
                raise TypeError("dimension_candidates must contain DimensionCandidate instances")
        object.__setattr__(self, "dimension_candidates", dimension_candidates)


@dataclass(frozen=True)
class SemanticProfile:
    domain: DatasetDomain
    entities: Tuple[EntityCandidate, ...] = field(default_factory=tuple)
    relationships: Tuple[RelationshipCandidate, ...] = field(default_factory=tuple)
    columns: Tuple[SemanticColumnProfile, ...] = field(default_factory=tuple)
    analytics_roles: AnalyticsRoleProfile = field(default_factory=AnalyticsRoleProfile)

    def __post_init__(self):
        if not isinstance(self.domain, DatasetDomain):
            raise TypeError("domain must be a DatasetDomain")

        entities = _tupleify(self.entities, "entities")
        for e in entities:
            if not isinstance(e, (EntityCandidate, SemanticEntity)):
                raise TypeError("entities must contain EntityCandidate or SemanticEntity instances")
        object.__setattr__(self, "entities", entities)

        relationships = _tupleify(self.relationships, "relationships")
        for r in relationships:
            if not isinstance(r, (RelationshipCandidate, SemanticRelationship)):
                raise TypeError(
                    "relationships must contain RelationshipCandidate or SemanticRelationship instances"
                )
        object.__setattr__(self, "relationships", relationships)

        columns = _tupleify(self.columns, "columns")
        for c in columns:
            if not isinstance(c, SemanticColumnProfile):
                raise TypeError("columns must contain SemanticColumnProfile instances")
        object.__setattr__(self, "columns", columns)

        if not isinstance(self.analytics_roles, AnalyticsRoleProfile):
            raise TypeError("analytics_roles must be an AnalyticsRoleProfile")
