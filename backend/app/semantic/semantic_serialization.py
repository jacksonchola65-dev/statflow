import math
from typing import Any, Dict, Type
from uuid import UUID

from .analytics_role_models import (
    Aggregation,
    AnalyticsRoleProfile,
    DimensionCandidate,
    DimensionType,
    MeasureCandidate,
)
from .entity_models import EntityKeyCandidate
from .semantic_models import (
    SemanticClassification,
    SemanticColumn,
    SemanticEntity,
    SemanticEvidence,
    SemanticProfile,
    SemanticRelationship,
    SemanticSuggestion,
)
from .semantic_profile_models import SemanticColumnProfile
from .semantic_profile_models import SemanticProfile as SemanticProfileModel
from .semantic_types import ColumnRole, DatasetDomain, SemanticType


def _enum_from_str(enum_cls: Type, value: str):
    try:
        return enum_cls(value)
    except Exception as exc:
        raise ValueError(f"Unknown enum value {value} for {enum_cls.__name__}") from exc


def to_dict(obj: Any) -> Dict[str, Any]:
    if isinstance(obj, SemanticColumn):
        return {
            "name": obj.name,
            "semantic_type": obj.semantic_type.value,
            "role": obj.role.value,
            "confidence": float(obj.confidence),
            "metadata": dict(obj.metadata or {}),
        }
    if isinstance(obj, SemanticEvidence):
        return {"source": obj.source, "score": float(obj.score), "description": obj.description}
    if isinstance(obj, SemanticSuggestion):
        return {"semantic_type": obj.semantic_type.value, "confidence": float(obj.confidence)}
    if isinstance(obj, SemanticClassification):
        return {
            "semantic_type": obj.semantic_type.value,
            "confidence": float(obj.confidence),
            "evidence": [to_dict(e) for e in obj.evidence],
            "detector": obj.detector,
            "suggestions": [to_dict(s) for s in obj.suggestions],
        }
    if isinstance(obj, SemanticEntity):
        return {
            "id": str(obj.id),
            "name": obj.name,
            "semantic_type": obj.semantic_type.value,
            "columns": [to_dict(c) for c in obj.columns],
            "confidence": float(obj.confidence),
            "metadata": dict(obj.metadata or {}),
        }
    if isinstance(obj, SemanticRelationship):
        return {
            "source_entity_id": str(obj.source_entity_id),
            "target_entity_id": str(obj.target_entity_id),
            "relationship_type": obj.relationship_type,
            "confidence": float(obj.confidence),
            "properties": dict(obj.properties or {}),
        }
    if isinstance(obj, MeasureCandidate):
        return {
            "name": obj.name,
            "semantic_type": obj.semantic_type.value,
            "aggregation": obj.aggregation.value,
            "confidence": float(obj.confidence),
            "cardinality_ratio": float(obj.cardinality_ratio),
            "null_ratio": float(obj.null_ratio),
            "evidence": [to_dict(e) for e in obj.evidence],
        }
    if isinstance(obj, DimensionCandidate):
        return {
            "name": obj.name,
            "semantic_type": obj.semantic_type.value,
            "dimension_type": obj.dimension_type.value,
            "confidence": float(obj.confidence),
            "cardinality_ratio": float(obj.cardinality_ratio),
            "null_ratio": float(obj.null_ratio),
            "evidence": [to_dict(e) for e in obj.evidence],
        }
    if isinstance(obj, AnalyticsRoleProfile):
        return {
            "measure_candidates": [to_dict(m) for m in obj.measure_candidates],
            "dimension_candidates": [to_dict(d) for d in obj.dimension_candidates],
        }
    if isinstance(obj, EntityKeyCandidate):
        return {
            "entity_name": obj.entity_name,
            "column_name": obj.column_name,
            "semantic_type": obj.semantic_type.value,
            "confidence": float(obj.confidence),
            "uniqueness_ratio": float(obj.uniqueness_ratio),
            "null_ratio": float(obj.null_ratio),
            "evidence": [to_dict(e) for e in obj.evidence],
        }
    if isinstance(obj, SemanticColumnProfile):
        return {
            "column_name": obj.column_name,
            "classifications": [to_dict(c) for c in obj.classifications],
            "key_candidates": [to_dict(k) for k in obj.key_candidates],
            "measure_candidates": [to_dict(m) for m in obj.measure_candidates],
            "dimension_candidates": [to_dict(d) for d in obj.dimension_candidates],
        }
    if isinstance(obj, SemanticProfileModel):
        return {
            "domain": obj.domain.value,
            "entities": [to_dict(e) for e in obj.entities],
            "relationships": [to_dict(r) for r in obj.relationships],
            "columns": [to_dict(c) for c in obj.columns],
            "analytics_roles": to_dict(obj.analytics_roles),
        }
    if isinstance(obj, SemanticProfile):
        return {
            "dataset_domain": obj.dataset_domain.value,
            "columns": [to_dict(c) for c in obj.columns],
            "entities": [to_dict(e) for e in obj.entities],
            "relationships": [to_dict(r) for r in obj.relationships],
            "overall_confidence": float(obj.overall_confidence),
            "metadata": dict(obj.metadata or {}),
        }
    raise TypeError(f"Unsupported type for serialization: {type(obj)}")


def _require(d: Dict, key: str):
    if key not in d:
        raise KeyError(f"Missing required field: {key}")
    return d[key]


def from_dict(cls: Type, data: Dict[str, Any]):
    if cls is SemanticColumn:
        _require(data, "name")
        name = data["name"]
        st = _enum_from_str(SemanticType, _require(data, "semantic_type"))
        role = _enum_from_str(ColumnRole, _require(data, "role"))
        conf = float(_require(data, "confidence"))
        if not math.isfinite(conf) or conf < 0.0 or conf > 1.0:
            raise ValueError("confidence must be finite between 0.0 and 1.0")
        metadata = data.get("metadata") or {}
        return SemanticColumn(
            name=name, semantic_type=st, role=role, confidence=conf, metadata=metadata
        )

    if cls is SemanticEvidence:
        _require(data, "source")
        _require(data, "score")
        score = float(data["score"])
        if not math.isfinite(score):
            raise ValueError("score must be finite and not NaN")
        return SemanticEvidence(
            source=data["source"], score=score, description=data.get("description")
        )

    if cls is SemanticSuggestion:
        st = _enum_from_str(SemanticType, _require(data, "semantic_type"))
        conf = float(_require(data, "confidence"))
        if not math.isfinite(conf) or conf < 0.0 or conf > 1.0:
            raise ValueError("confidence must be finite between 0.0 and 1.0")
        return SemanticSuggestion(semantic_type=st, confidence=conf)

    if cls is SemanticClassification:
        st = _enum_from_str(SemanticType, _require(data, "semantic_type"))
        conf = float(_require(data, "confidence"))
        if not math.isfinite(conf) or conf < 0.0 or conf > 1.0:
            raise ValueError("confidence must be finite between 0.0 and 1.0")
        evidence_list = [from_dict(SemanticEvidence, e) for e in data.get("evidence", [])]
        suggestions_list = [from_dict(SemanticSuggestion, s) for s in data.get("suggestions", [])]
        detector = data.get("detector")
        return SemanticClassification(
            semantic_type=st,
            confidence=conf,
            evidence=tuple(evidence_list),
            detector=detector,
            suggestions=tuple(suggestions_list),
        )

    if cls is SemanticEntity:
        _require(data, "id")
        _require(data, "name")
        st = _enum_from_str(SemanticType, _require(data, "semantic_type"))
        cols = tuple(from_dict(SemanticColumn, c) for c in data.get("columns", []))
        conf = float(data.get("confidence", 0.0))
        if not math.isfinite(conf) or conf < 0.0 or conf > 1.0:
            raise ValueError("confidence must be finite between 0.0 and 1.0")
        metadata = data.get("metadata") or {}
        return SemanticEntity(
            id=UUID(data["id"]),
            name=data["name"],
            semantic_type=st,
            columns=cols,
            confidence=conf,
            metadata=metadata,
        )

    if cls is SemanticRelationship:
        _require(data, "source_entity_id")
        _require(data, "target_entity_id")
        _require(data, "relationship_type")
        conf = float(data.get("confidence", 0.0))
        if not math.isfinite(conf) or conf < 0.0 or conf > 1.0:
            raise ValueError("confidence must be finite between 0.0 and 1.0")
        props = data.get("properties") or {}
        return SemanticRelationship(
            source_entity_id=UUID(data["source_entity_id"]),
            target_entity_id=UUID(data["target_entity_id"]),
            relationship_type=data["relationship_type"],
            confidence=conf,
            properties=props,
        )

    if cls is MeasureCandidate:
        return MeasureCandidate(
            name=_require(data, "name"),
            semantic_type=_enum_from_str(SemanticType, _require(data, "semantic_type")),
            aggregation=_enum_from_str(Aggregation, _require(data, "aggregation")),
            confidence=float(_require(data, "confidence")),
            cardinality_ratio=float(_require(data, "cardinality_ratio")),
            null_ratio=float(_require(data, "null_ratio")),
            evidence=tuple(from_dict(SemanticEvidence, e) for e in data.get("evidence", [])),
        )

    if cls is DimensionCandidate:
        return DimensionCandidate(
            name=_require(data, "name"),
            semantic_type=_enum_from_str(SemanticType, _require(data, "semantic_type")),
            dimension_type=_enum_from_str(DimensionType, _require(data, "dimension_type")),
            confidence=float(_require(data, "confidence")),
            cardinality_ratio=float(_require(data, "cardinality_ratio")),
            null_ratio=float(_require(data, "null_ratio")),
            evidence=tuple(from_dict(SemanticEvidence, e) for e in data.get("evidence", [])),
        )

    if cls is AnalyticsRoleProfile:
        measures = tuple(from_dict(MeasureCandidate, m) for m in data.get("measure_candidates", []))
        dimensions = tuple(
            from_dict(DimensionCandidate, d) for d in data.get("dimension_candidates", [])
        )
        return AnalyticsRoleProfile(measure_candidates=measures, dimension_candidates=dimensions)

    if cls is EntityKeyCandidate:
        return EntityKeyCandidate(
            entity_name=_require(data, "entity_name"),
            column_name=_require(data, "column_name"),
            semantic_type=_enum_from_str(SemanticType, _require(data, "semantic_type")),
            confidence=float(_require(data, "confidence")),
            uniqueness_ratio=float(_require(data, "uniqueness_ratio")),
            null_ratio=float(_require(data, "null_ratio")),
            evidence=tuple(from_dict(SemanticEvidence, e) for e in data.get("evidence", [])),
        )

    if cls is SemanticColumnProfile:
        return SemanticColumnProfile(
            column_name=_require(data, "column_name"),
            classifications=tuple(
                from_dict(SemanticClassification, c) for c in data.get("classifications", [])
            ),
            key_candidates=tuple(
                from_dict(EntityKeyCandidate, k) for k in data.get("key_candidates", [])
            ),
            measure_candidates=tuple(
                from_dict(MeasureCandidate, m) for m in data.get("measure_candidates", [])
            ),
            dimension_candidates=tuple(
                from_dict(DimensionCandidate, d) for d in data.get("dimension_candidates", [])
            ),
        )

    if cls is SemanticProfileModel:
        return SemanticProfileModel(
            domain=_enum_from_str(DatasetDomain, _require(data, "domain")),
            entities=tuple(from_dict(SemanticEntity, e) for e in data.get("entities", [])),
            relationships=tuple(
                from_dict(SemanticRelationship, r) for r in data.get("relationships", [])
            ),
            columns=tuple(from_dict(SemanticColumnProfile, c) for c in data.get("columns", [])),
            analytics_roles=from_dict(AnalyticsRoleProfile, _require(data, "analytics_roles")),
        )

    if cls is SemanticProfile:
        domain = _enum_from_str(DatasetDomain, _require(data, "dataset_domain"))
        cols = tuple(from_dict(SemanticColumn, c) for c in data.get("columns", []))
        ents = tuple(from_dict(SemanticEntity, e) for e in data.get("entities", []))
        rels = tuple(from_dict(SemanticRelationship, r) for r in data.get("relationships", []))
        oc = float(data.get("overall_confidence", 0.0))
        if not math.isfinite(oc) or oc < 0.0 or oc > 1.0:
            raise ValueError("overall_confidence must be finite between 0.0 and 1.0")
        metadata = data.get("metadata") or {}
        return SemanticProfile(
            dataset_domain=domain,
            columns=cols,
            entities=ents,
            relationships=rels,
            overall_confidence=oc,
            metadata=metadata,
        )

    raise TypeError(f"Unsupported type for deserialization: {cls}")
