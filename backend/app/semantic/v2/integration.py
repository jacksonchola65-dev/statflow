"""Controlled integration helpers for running fused native v2 semantic pipeline
from FileInspectionService without changing public APIs.
"""
from __future__ import annotations

import os
from typing import Iterable

from app.semantic.v2.feature_extraction import FeatureExtractionPipeline
from app.semantic.v2.semantic_context import SemanticContext
from app.semantic.v2.native_detection_pipeline import NativeDetectionPipeline
from app.semantic.consensus_engine import ConsensusEngine
from app.semantic.semantic_profile_builder import ColumnClassification, DomainDetectionResult, SemanticProfileBuilder
from app.semantic.entity_candidate_detector import EntityColumnInput, EntityCandidateDetector
from app.semantic.entity_key_detector import EntityKeyColumnInput, EntityKeyDetectionInput, EntityKeyDetector
from app.semantic.relationship_detector import RelationshipColumnInput, RelationshipDetectionInput, RelationshipDetector
from app.semantic.measure_detector import MeasureColumnInput, MeasureDetector
from app.semantic.dimension_detector import DimensionColumnInput, DimensionDetector
from app.semantic.analytics_role_service import AnalyticsRoleService
from app.semantic.semantic_serialization import to_dict as semantic_to_dict
from app.semantic.semantic_types import DatasetDomain


def compose_semantic_profile_from_columns(columns: Iterable) -> dict:
    """Compose a serialized semantic profile using native v2 fused pipeline.

    Args:
        columns: Iterable of SourceColumn-like objects with fields: name, sample_values, nullable

    Returns:
        dict: serialized semantic profile (or empty dict on error)
    """
    try:
        # Feature extraction: build ColumnFeatureContext for each column once
        col_contexts = []
        for c in columns:
            # FeatureExtractionPipeline accepts (column_name, tuple(values))
            ctx = FeatureExtractionPipeline.extract(c.name, tuple(c.sample_values))
            col_contexts.append(ctx)

        sem_ctx = SemanticContext(columns=tuple(col_contexts))

        pipeline = NativeDetectionPipeline()
        results_batch = pipeline.run(sem_ctx, fused=True)

        # Merge per-column detector results to SemanticClassification list
        batch_classifications = []
        for res_list in results_batch:
            merged = ConsensusEngine.merge(list(res_list))
            batch_classifications.append(tuple(merged))

        col_classifications = [ColumnClassification(column_name=c.name, classifications=tuple(classifications)) for c, classifications in zip(columns, batch_classifications)]

        # Entities, keys, relationships, measures, dimensions, analytics
        entity_inputs = tuple(EntityColumnInput(column_name=cc.column_name, classifications=cc.classifications) for cc in col_classifications)
        entities = EntityCandidateDetector.discover(entity_inputs)

        ek_inputs = []
        rel_inputs = []
        measure_inputs = []
        dimension_inputs = []
        for sc in columns:
            samples = sc.sample_values
            sample_size = len(samples)
            unique_ratio = (len(set(samples)) / sample_size) if sample_size > 0 else 0.0
            null_ratio = 1.0 if sc.nullable else 0.0
            cls = tuple(next((cc.classifications for cc in col_classifications if cc.column_name == sc.name), ()))
            ek_inputs.append(EntityKeyColumnInput(column_name=sc.name, classifications=cls, uniqueness_ratio=unique_ratio, null_ratio=null_ratio))
            rel_inputs.append(RelationshipColumnInput(column_name=sc.name, classifications=cls, uniqueness_ratio=unique_ratio, null_ratio=null_ratio))
            measure_inputs.append(MeasureColumnInput(column_name=sc.name, classifications=cls, cardinality_ratio=unique_ratio, null_ratio=null_ratio))
            dimension_inputs.append(DimensionColumnInput(column_name=sc.name, classifications=cls, cardinality_ratio=unique_ratio, null_ratio=null_ratio))

        keys = EntityKeyDetector.discover(EntityKeyDetectionInput(entities=entities, columns=tuple(ek_inputs)))
        rels = RelationshipDetector.discover(RelationshipDetectionInput(entities=entities, keys=keys, columns=tuple(rel_inputs)))
        measures = MeasureDetector.discover(tuple(measure_inputs))
        dimensions = DimensionDetector.discover(tuple(dimension_inputs))
        analytics_roles = AnalyticsRoleService.compose(measures, dimensions)

        domain_result = DomainDetectionResult(domain=DatasetDomain.GENERAL)
        profile = SemanticProfileBuilder.compose(domain_result, entities, rels, keys, analytics_roles, tuple(col_classifications))
        return semantic_to_dict(profile)
    except Exception:
        # Best-effort: do not let semantics break inspection
        return {}


def get_semantic_engine_version() -> str:
    return os.getenv("SEMANTIC_ENGINE_VERSION", "v2")


__all__ = ["compose_semantic_profile_from_columns", "get_semantic_engine_version"]
