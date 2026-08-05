import copy
import time

import pytest
from app.semantic.entity_candidate_detector import EntityCandidateDetector, EntityColumnInput
from app.semantic.entity_key_detector import (
    EntityKeyColumnInput,
    EntityKeyDetectionInput,
    EntityKeyDetector,
)
from app.semantic.relationship_detector import (
    RelationshipColumnInput,
    RelationshipDetectionInput,
    RelationshipDetector,
)
from app.semantic.semantic_models import SemanticClassification, SemanticEvidence
from app.semantic.semantic_types import SemanticType


def sc(t, c):
    return SemanticClassification(
        semantic_type=t,
        confidence=c,
        evidence=(SemanticEvidence(source="d", score=float(c), description="e"),),
        detector="det",
    )


def run_pipeline(entity_cols, key_cols, rel_cols):
    # entity detection
    entities = EntityCandidateDetector.discover(tuple(entity_cols))
    # key detection
    ek_inputs = tuple(key_cols)
    key_candidates = EntityKeyDetector.discover(
        EntityKeyDetectionInput(entities=entities, columns=ek_inputs)
    )
    # relationship detection
    rel_candidates = RelationshipDetector.discover(
        RelationshipDetectionInput(entities=entities, keys=key_candidates, columns=tuple(rel_cols))
    )
    return entities, key_candidates, rel_candidates


def make_entity_col(name):
    # mark as entity-bearing using ORGANIZATION for generic entities
    return EntityColumnInput(
        column_name=f"{name}_name", classifications=(sc(SemanticType.ORGANIZATION, 0.9),)
    )


def make_key_col(name):
    return EntityKeyColumnInput(
        column_name=f"{name}_id",
        classifications=(sc(SemanticType.IDENTIFIER, 0.95),),
        uniqueness_ratio=0.99,
        null_ratio=0.0,
    )


def make_rel_col(target, source):
    # convention: target_source_id
    return RelationshipColumnInput(
        column_name=f"{target}_{source}_id",
        classifications=(sc(SemanticType.IDENTIFIER, 0.85),),
        uniqueness_ratio=0.9,
        null_ratio=0.1,
    )


def test_retail_healthcare_education_hr_government_and_edge_cases():
    scenarios = []

    # 1 Retail
    retail_entities = ["customer", "product", "order"]
    retail_entity_cols = [make_entity_col(n) for n in retail_entities]
    retail_key_cols = [make_key_col(n) for n in retail_entities]
    retail_rel_cols = [make_rel_col("order", "customer"), make_rel_col("order", "product")]
    scenarios.append((retail_entity_cols, retail_key_cols, retail_rel_cols, 3, 3, 2))

    # 2 Healthcare
    hc = ["patient", "doctor", "hospital", "appointment"]
    hc_entity_cols = [make_entity_col(n) for n in hc]
    hc_key_cols = [make_key_col(n) for n in hc]
    hc_rel_cols = [
        make_rel_col("appointment", "patient"),
        make_rel_col("appointment", "doctor"),
        make_rel_col("appointment", "hospital"),
    ]
    scenarios.append((hc_entity_cols, hc_key_cols, hc_rel_cols, 4, 4, 3))

    # 3 Education
    ed = ["student", "course", "lecturer", "enrollment"]
    ed_entity_cols = [make_entity_col(n) for n in ed]
    ed_key_cols = [make_key_col(n) for n in ed]
    ed_rel_cols = [
        make_rel_col("enrollment", "student"),
        make_rel_col("enrollment", "course"),
        make_rel_col("enrollment", "lecturer"),
    ]
    scenarios.append((ed_entity_cols, ed_key_cols, ed_rel_cols, 4, 4, 3))

    # 4 HR
    hr = ["employee", "department", "payroll"]
    hr_entity_cols = [make_entity_col(n) for n in hr]
    hr_key_cols = [make_key_col(n) for n in hr]
    hr_rel_cols = [make_rel_col("payroll", "employee"), make_rel_col("payroll", "department")]
    scenarios.append((hr_entity_cols, hr_key_cols, hr_rel_cols, 3, 3, 2))

    # 5 Government
    gov = ["citizen", "district", "province", "permit"]
    gov_entity_cols = [make_entity_col(n) for n in gov]
    gov_key_cols = [make_key_col(n) for n in gov]
    gov_rel_cols = [
        make_rel_col("permit", "citizen"),
        make_rel_col("permit", "district"),
        make_rel_col("permit", "province"),
    ]
    scenarios.append((gov_entity_cols, gov_key_cols, gov_rel_cols, 4, 4, 3))

    # 6 No entities
    no_entity_cols = [
        EntityColumnInput(column_name="metric_1", classifications=(sc(SemanticType.NUMBER, 0.9),))
    ]
    scenarios.append((no_entity_cols, [], [], 0, 0, 0))

    # 7 Entities without keys
    ek_entities = ["a", "b"]
    ek_entity_cols = [make_entity_col(n) for n in ek_entities]
    scenarios.append((ek_entity_cols, [], [], 2, 0, 0))

    # 8 Self-reference protection
    s_entity_cols = [make_entity_col("x")]
    s_key_cols = [make_key_col("x")]
    s_rel_cols = [make_rel_col("x", "x")]
    scenarios.append((s_entity_cols, s_key_cols, s_rel_cols, 1, 1, 0))

    # 9 Duplicate suppression
    d_entities = ["p", "q"]
    d_entity_cols = [make_entity_col(n) for n in d_entities]
    d_key_cols = [make_key_col(n) for n in d_entities]
    # duplicate relationship columns (same name) with same classification
    dup_col1 = make_rel_col("p", "q")
    dup_col2 = make_rel_col("p", "q")
    scenarios.append((d_entity_cols, d_key_cols, [dup_col1, dup_col2], 2, 2, 1))

    # run scenarios
    for entity_cols, key_cols, rel_cols, exp_entities, exp_keys, exp_rels in scenarios:
        # keep copies for immutability check
        e_cols_copy = copy.deepcopy(entity_cols)
        k_cols_copy = copy.deepcopy(key_cols)
        r_cols_copy = copy.deepcopy(rel_cols)

        entities, keys, rels = run_pipeline(entity_cols, key_cols, rel_cols)

        assert len(entities) == exp_entities
        assert len(keys) == exp_keys
        # number of relationships >= expected (some scenarios expect 0 relationships)
        if exp_rels == 0:
            assert len(rels) == 0
        else:
            assert len(rels) >= exp_rels

        # determinism: run again
        entities2, keys2, rels2 = run_pipeline(entity_cols, key_cols, rel_cols)
        assert entities == entities2
        assert keys == keys2
        assert rels == rels2

        # immutability
        assert entity_cols == e_cols_copy
        assert key_cols == k_cols_copy
        assert rel_cols == r_cols_copy


@pytest.mark.performance
def test_large_metadata_and_performance():
    # 100 entities, 100 keys, 100 relationship columns
    n = 100
    entity_names = [f"ent_{i}" for i in range(n)]
    entity_cols = [make_entity_col(nm) for nm in entity_names]
    key_cols = [make_key_col(nm) for nm in entity_names]
    rel_cols = [make_rel_col(f"ent_{i}", f"ent_{i}") for i in range(n)]

    # but self references will be suppressed; use different target-source pairs for half
    for i in range(0, n, 2):
        rel_cols[i] = make_rel_col(f"ent_{i}", f"ent_{(i + 1) % n}")

    # run once to warm-up
    for _ in range(5):
        _ = run_pipeline(entity_cols, key_cols, rel_cols)

    runs = 20
    start = time.perf_counter()
    for _ in range(runs):
        _ = run_pipeline(entity_cols, key_cols, rel_cols)
    end = time.perf_counter()
    avg = (end - start) / runs
    assert avg < 0.01
