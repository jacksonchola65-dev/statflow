from dataclasses import dataclass, field
from typing import Tuple, Iterable

from .analytics_role_models import AnalyticsRoleProfile, DimensionCandidate, MeasureCandidate
from .entity_models import EntityCandidate, EntityKeyCandidate, RelationshipCandidate
from .semantic_models import SemanticClassification, SemanticEntity
from .semantic_profile_models import SemanticColumnProfile, SemanticProfile
from .semantic_types import DatasetDomain


@dataclass(frozen=True)
class DomainDetectionResult:
    domain: DatasetDomain

    def __post_init__(self):
        if not isinstance(self.domain, DatasetDomain):
            raise TypeError("domain must be a DatasetDomain")


@dataclass(frozen=True)
class ColumnClassification:
    column_name: str
    classifications: Tuple[SemanticClassification, ...] = field(default_factory=tuple)

    def __post_init__(self):
        if not isinstance(self.column_name, str):
            raise TypeError("column_name must be a string")
        if not self.column_name.strip():
            raise ValueError("column_name must be a non-empty string")
        object.__setattr__(self, "column_name", self.column_name.strip())

        if not isinstance(self.classifications, Iterable):
            raise TypeError("classifications must be iterable")
        cls = tuple(self.classifications)
        for c in cls:
            if not isinstance(c, SemanticClassification):
                raise TypeError("classifications must contain SemanticClassification instances")
        object.__setattr__(self, "classifications", cls)


class SemanticProfileBuilder:
    @staticmethod
    def compose(
        domain_result: DomainDetectionResult,
        entities: Tuple[EntityCandidate, ...],
        relationships: Tuple[RelationshipCandidate, ...],
        key_candidates: Tuple[EntityKeyCandidate, ...],
        analytics_roles: AnalyticsRoleProfile,
        column_classifications: Tuple[ColumnClassification, ...],
    ) -> SemanticProfile:
        if not isinstance(domain_result, DomainDetectionResult):
            raise TypeError("domain_result must be a DomainDetectionResult")

        if not isinstance(entities, tuple):
            raise TypeError("entities must be a tuple of EntityCandidate")
        for e in entities:
            if not isinstance(e, EntityCandidate):
                raise TypeError("entities must contain EntityCandidate instances")

        if not isinstance(relationships, tuple):
            raise TypeError("relationships must be a tuple of RelationshipCandidate")
        for r in relationships:
            if not isinstance(r, RelationshipCandidate):
                raise TypeError("relationships must contain RelationshipCandidate instances")

        if not isinstance(key_candidates, tuple):
            raise TypeError("key_candidates must be a tuple of EntityKeyCandidate")
        for k in key_candidates:
            if not isinstance(k, EntityKeyCandidate):
                raise TypeError("key_candidates must contain EntityKeyCandidate instances")

        if not isinstance(analytics_roles, AnalyticsRoleProfile):
            raise TypeError("analytics_roles must be an AnalyticsRoleProfile")

        if not isinstance(column_classifications, tuple):
            raise TypeError("column_classifications must be a tuple of ColumnClassification")
        for cc in column_classifications:
            if not isinstance(cc, ColumnClassification):
                raise TypeError("column_classifications must contain ColumnClassification instances")

        keys_by_column: dict[str, list[EntityKeyCandidate]] = {}
        for key in key_candidates:
            keys_by_column.setdefault(key.column_name, []).append(key)

        measures_by_column: dict[str, list[MeasureCandidate]] = {}
        for measure in analytics_roles.measure_candidates:
            measures_by_column.setdefault(measure.name, []).append(measure)

        dimensions_by_column: dict[str, list[DimensionCandidate]] = {}
        for dimension in analytics_roles.dimension_candidates:
            dimensions_by_column.setdefault(dimension.name, []).append(dimension)

        columns: list[SemanticColumnProfile] = []
        for classification in column_classifications:
            columns.append(
                SemanticColumnProfile(
                    column_name=classification.column_name,
                    classifications=classification.classifications,
                    key_candidates=tuple(keys_by_column.get(classification.column_name, [])),
                    measure_candidates=tuple(measures_by_column.get(classification.column_name, [])),
                    dimension_candidates=tuple(dimensions_by_column.get(classification.column_name, [])),
                )
            )

        return SemanticProfile(
            domain=domain_result.domain,
            entities=entities,
            relationships=relationships,
            columns=tuple(columns),
            analytics_roles=analytics_roles,
        )
