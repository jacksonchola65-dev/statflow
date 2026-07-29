import math
from typing import List

import pytest

from app.semantic.detection_pipeline import SemanticDetectionPipeline
from app.semantic.consensus_engine import ConsensusEngine
from app.semantic.v2.native_detection_pipeline import NativeDetectionPipeline
from app.semantic.detectors.base import DetectorInput
from app.semantic.detectors.value_sampling_detector import ValueSamplingDetector
from app.semantic.detectors.regex_detector import RegexSemanticDetector
from app.semantic.detectors.dictionary_detector import DictionarySemanticDetector
from app.semantic.v2.feature_models import ColumnFeatureContext, LightValueFeatures
from app.semantic.v2.semantic_context import SemanticContext
from app.semantic.semantic_profile_builder import (
    ColumnClassification,
    DomainDetectionResult,
    SemanticProfileBuilder,
)
from app.semantic.entity_candidate_detector import EntityColumnInput, EntityCandidateDetector
from app.semantic.entity_key_detector import EntityKeyColumnInput, EntityKeyDetectionInput, EntityKeyDetector
from app.semantic.relationship_detector import RelationshipColumnInput, RelationshipDetectionInput, RelationshipDetector
from app.semantic.measure_detector import MeasureColumnInput, MeasureDetector
from app.semantic.dimension_detector import DimensionColumnInput, DimensionDetector
from app.semantic.analytics_role_service import AnalyticsRoleService
from app.semantic.semantic_serialization import to_dict as semantic_to_dict, from_dict as semantic_from_dict
from app.semantic.semantic_types import DatasetDomain

from backend.tests.semantic.v2.differential_cases import all_cases


SEED = 12345
GENERATED_COUNT = 1000


def _make_light(v: str) -> LightValueFeatures:
    raw = v
    cleaned = raw.strip()
    lowered = cleaned.lower()
    is_empty = cleaned == ""
    is_int = False
    is_dec = False
    pn = None
    try:
        if cleaned != "":
            if cleaned.lstrip("+-").isdigit():
                is_int = True
                pn = float(int(cleaned))
            else:
                pn = float(cleaned)
                is_dec = True
    except Exception:
        pn = None

    return LightValueFeatures(raw_value=raw, cleaned_value=cleaned, lowered_value=lowered, is_empty=is_empty, is_integer=is_int, is_decimal=is_dec, parsed_number=(float(pn) if pn is not None else None))


def _build_inputs(case) -> (DetectorInput, ColumnFeatureContext):
    cleaned = []
    for v in case.values:
        if v is None:
            continue
        s = v if isinstance(v, str) else str(v)
        if s.strip() == "":
            continue
        cleaned.append(s)
        if len(cleaned) >= 100:
            break

    detector_input = DetectorInput(column_name=case.column_name or "", values=tuple(cleaned), inferred_type=None)

    light_vals = tuple(_make_light(s) for s in cleaned)
    non_null = len(light_vals)
    null_count = sum(1 for v in case.values if v is None or (isinstance(v, str) and v.strip() == ""))
    total = len(case.values)
    unique_count = len(set(l.cleaned_value for l in light_vals))
    cardinality_ratio = float(unique_count / non_null) if non_null > 0 else 0.0
    null_ratio = float(null_count / total) if total > 0 else 0.0

    col_ctx = ColumnFeatureContext(
        column_name=case.column_name or "",
        values=light_vals,
        null_count=null_count,
        non_null_count=non_null,
        unique_count=unique_count,
        cardinality_ratio=cardinality_ratio,
        null_ratio=null_ratio,
    )

    return detector_input, col_ctx


def _format_classifications(cls_list) -> List[dict]:
    return [semantic_to_dict(c) for c in cls_list]


def test_differential_validation_all_cases():
    cases = all_cases(seed=SEED, generated=GENERATED_COUNT)

    v1_pipeline = SemanticDetectionPipeline([RegexSemanticDetector(), DictionarySemanticDetector(), ValueSamplingDetector()])
    v2_pipeline = NativeDetectionPipeline()

    total_det_comparisons = 0
    total_profile_comparisons = 0

    for case in cases:
        det_input, col_ctx = _build_inputs(case)

        v1_out = v1_pipeline.run(det_input)

        ctx = SemanticContext(columns=(col_ctx,))
        v2_results_batch = v2_pipeline.run(ctx, fused=True)
        v2_results = v2_results_batch[0] if v2_results_batch else []
        v2_merged = ConsensusEngine.merge(list(v2_results))

        total_det_comparisons += 1

        if v1_out != v2_merged:
            v1_ser = _format_classifications(v1_out)
            v2_ser = _format_classifications(v2_merged)
            first_diff = None
            if len(v1_out) != len(v2_merged):
                first_diff = f"result_count: v1={len(v1_out)} v2={len(v2_merged)}"
            else:
                for i, (a, b) in enumerate(zip(v1_out, v2_merged)):
                    if a.semantic_type != b.semantic_type:
                        first_diff = f"semantic_type at index {i}: v1={a.semantic_type} v2={b.semantic_type}"
                        break
                    if float(a.confidence) != float(b.confidence):
                        first_diff = f"confidence at index {i}: v1={a.confidence} v2={b.confidence}"
                        break
                    if a.detector != b.detector:
                        first_diff = f"detector at index {i}: v1={a.detector} v2={b.detector}"
                        break
                    if tuple((e.source, float(e.score), e.description) for e in a.evidence) != tuple((e.source, float(e.score), e.description) for e in b.evidence):
                        first_diff = f"evidence at index {i}: v1={a.evidence} v2={b.evidence}"
                        break
            msg = (
                f"Case ID: {case.case_id}\n"
                f"Column Name: {case.column_name!r}\n"
                f"Input Values: {list(case.values)!r}\n"
                f"v1_output: {v1_ser!r}\n"
                f"v2_output: {v2_ser!r}\n"
                f"First differing field: {first_diff}\n"
            )
            pytest.fail(msg)

        if not (case.column_name and case.column_name.strip()):
            continue

        col_class_v1 = ColumnClassification(column_name=case.column_name, classifications=tuple(v1_out))
        col_class_v2 = ColumnClassification(column_name=case.column_name, classifications=tuple(v2_merged))

        entities_v1 = EntityCandidateDetector.discover((EntityColumnInput(column_name=col_class_v1.column_name, classifications=col_class_v1.classifications),))
        entities_v2 = EntityCandidateDetector.discover((EntityColumnInput(column_name=col_class_v2.column_name, classifications=col_class_v2.classifications),))

        sample_size = len([v for v in case.values if v is not None and (not isinstance(v, str) or v.strip() != "")])
        unique_ratio = (len(set([v for v in case.values if v is not None and (not isinstance(v, str) or v.strip() != "")])) / sample_size) if sample_size > 0 else 0.0
        null_ratio = 1.0 if all((v is None or (isinstance(v, str) and v.strip() == "")) for v in case.values) else 0.0

        ek_inputs_v1 = (EntityKeyColumnInput(column_name=col_class_v1.column_name, classifications=col_class_v1.classifications, uniqueness_ratio=unique_ratio, null_ratio=null_ratio),)
        ek_inputs_v2 = (EntityKeyColumnInput(column_name=col_class_v2.column_name, classifications=col_class_v2.classifications, uniqueness_ratio=unique_ratio, null_ratio=null_ratio),)

        keys_v1 = EntityKeyDetector.discover(EntityKeyDetectionInput(entities=entities_v1, columns=ek_inputs_v1))
        keys_v2 = EntityKeyDetector.discover(EntityKeyDetectionInput(entities=entities_v2, columns=ek_inputs_v2))

        rel_inputs_v1 = (RelationshipColumnInput(column_name=col_class_v1.column_name, classifications=col_class_v1.classifications, uniqueness_ratio=unique_ratio, null_ratio=null_ratio),)
        rel_inputs_v2 = (RelationshipColumnInput(column_name=col_class_v2.column_name, classifications=col_class_v2.classifications, uniqueness_ratio=unique_ratio, null_ratio=null_ratio),)

        rels_v1 = RelationshipDetector.discover(RelationshipDetectionInput(entities=entities_v1, keys=keys_v1, columns=rel_inputs_v1))
        rels_v2 = RelationshipDetector.discover(RelationshipDetectionInput(entities=entities_v2, keys=keys_v2, columns=rel_inputs_v2))

        measures_v1 = MeasureDetector.discover((
            MeasureColumnInput(column_name=col_class_v1.column_name, classifications=col_class_v1.classifications, cardinality_ratio=unique_ratio, null_ratio=null_ratio),
        ))
        measures_v2 = MeasureDetector.discover((
            MeasureColumnInput(column_name=col_class_v2.column_name, classifications=col_class_v2.classifications, cardinality_ratio=unique_ratio, null_ratio=null_ratio),
        ))

        dims_v1 = DimensionDetector.discover((
            DimensionColumnInput(column_name=col_class_v1.column_name, classifications=col_class_v1.classifications, cardinality_ratio=unique_ratio, null_ratio=null_ratio),
        ))
        dims_v2 = DimensionDetector.discover((
            DimensionColumnInput(column_name=col_class_v2.column_name, classifications=col_class_v2.classifications, cardinality_ratio=unique_ratio, null_ratio=null_ratio),
        ))

        analytics_v1 = AnalyticsRoleService.compose(measures_v1, dims_v1)
        analytics_v2 = AnalyticsRoleService.compose(measures_v2, dims_v2)

        profile_v1 = SemanticProfileBuilder.compose(DomainDetectionResult(domain=DatasetDomain.GENERAL), entities_v1, rels_v1, keys_v1, analytics_v1, (col_class_v1,))
        profile_v2 = SemanticProfileBuilder.compose(DomainDetectionResult(domain=DatasetDomain.GENERAL), entities_v2, rels_v2, keys_v2, analytics_v2, (col_class_v2,))

        dict_v1 = semantic_to_dict(profile_v1)
        dict_v2 = semantic_to_dict(profile_v2)
        total_profile_comparisons += 1
        if dict_v1 != dict_v2:
            pytest.fail(f"Profile mismatch for case {case.case_id}: v1={dict_v1!r} v2={dict_v2!r}")

        rt = semantic_from_dict(type(profile_v1), dict_v1)
        rt_dict = semantic_to_dict(rt)
        if dict_v1 != rt_dict:
            pytest.fail(f"Serialization round-trip failed for case {case.case_id}")

    assert total_det_comparisons == len(cases)
    expected_profiles = sum(1 for c in cases if c.column_name and c.column_name.strip())
    assert total_profile_comparisons == expected_profiles
