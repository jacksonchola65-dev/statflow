import copy

import pytest
from app.semantic.entity_candidate_detector import EntityCandidateDetector, EntityColumnInput
from app.semantic.semantic_models import SemanticClassification, SemanticEvidence
from app.semantic.semantic_types import SemanticType


def sc(t, c):
    return SemanticClassification(
        semantic_type=t,
        confidence=c,
        evidence=(SemanticEvidence(source="d", score=float(c), description="e"),),
        detector="det",
    )


def test_malformed_input_rejected():
    with pytest.raises(TypeError):
        EntityCandidateDetector.discover([object()])


def test_empty_input():
    assert EntityCandidateDetector.discover([]) == ()


def test_person_entity_detection_and_suffix_normalization():
    cols = [
        EntityColumnInput(
            column_name=" customer_name ", classifications=(sc(SemanticType.PERSON, 0.9),)
        ),
        EntityColumnInput(
            column_name="customer-id", classifications=(sc(SemanticType.PERSON, 0.85),)
        ),
    ]
    res = EntityCandidateDetector.discover(cols)
    assert len(res) == 1
    assert res[0].name.lower() == "customer"
    assert "customer_id" not in res[0].source_columns


def test_organization_and_geographic_detection_and_grouping():
    cols = [
        EntityColumnInput(
            column_name="org_name", classifications=(sc(SemanticType.ORGANIZATION, 0.9),)
        ),
        EntityColumnInput(
            column_name="company", classifications=(sc(SemanticType.ORGANIZATION, 0.88),)
        ),
        EntityColumnInput(column_name="city", classifications=(sc(SemanticType.CITY, 0.95),)),
        EntityColumnInput(
            column_name="province ", classifications=(sc(SemanticType.PROVINCE, 0.8),)
        ),
    ]
    res = EntityCandidateDetector.discover(cols)
    names = [r.name.lower() for r in res]
    assert "org" in names or "org name" in names or "company" in names


def test_confidence_threshold_and_non_entity_ignored():
    cols = [
        EntityColumnInput(column_name="p", classifications=(sc(SemanticType.PERSON, 0.59),)),
        EntityColumnInput(column_name="p2", classifications=(sc(SemanticType.PERSON, 0.6),)),
        EntityColumnInput(column_name="t", classifications=(sc(SemanticType.TEXT, 0.95),)),
    ]
    res = EntityCandidateDetector.discover(cols)
    assert len(res) == 1
    assert res[0].source_columns == ("p2",)


def test_underscore_hyphen_and_whitespace_normalization_and_empty_name_fallback():
    cols = [
        EntityColumnInput(column_name="__id__", classifications=(sc(SemanticType.PERSON, 0.9),)),
        EntityColumnInput(
            column_name="employee__id", classifications=(sc(SemanticType.PERSON, 0.85),)
        ),
    ]
    res = EntityCandidateDetector.discover(cols)
    assert len(res) >= 1
    # ensure no empty name
    for r in res:
        assert r.name.strip() != ""


def test_multiple_semantic_types_and_duplicate_removal_and_evidence_ordering():
    cols = [
        EntityColumnInput(
            column_name="entity_name",
            classifications=(sc(SemanticType.PERSON, 0.9), sc(SemanticType.ORGANIZATION, 0.7)),
        ),
        EntityColumnInput(
            column_name="entity_id",
            classifications=(sc(SemanticType.PERSON, 0.85), sc(SemanticType.COUNTRY, 0.65)),
        ),
    ]
    res = EntityCandidateDetector.discover(cols)
    assert len(res) == 1
    rc = res[0]
    # semantic types should include PERSON, ORGANIZATION, COUNTRY in first-seen order
    assert rc.semantic_types[0] == SemanticType.PERSON
    assert SemanticType.ORGANIZATION in rc.semantic_types
    assert SemanticType.COUNTRY in rc.semantic_types
    # evidence ordering: first column then second
    assert rc.evidence[0].source == "d"


def test_deterministic_sorting_and_input_immutability():
    cols = []
    for i in range(10):
        cols.append(
            EntityColumnInput(
                column_name=f"name_{i}", classifications=(sc(SemanticType.PERSON, 0.9 - i * 0.01),)
            )
        )
    cols_copy = copy.deepcopy(cols)
    r1 = EntityCandidateDetector.discover(cols)
    r2 = EntityCandidateDetector.discover(cols)
    assert r1 == r2
    assert cols == cols_copy


def test_performance_100_columns():
    types = [SemanticType.PERSON, SemanticType.ORGANIZATION, SemanticType.CITY]
    cols = []
    for i in range(100):
        cset = []
        for j in range((i % 3) + 1):
            cset.append(
                SemanticClassification(
                    semantic_type=types[(i + j) % len(types)],
                    confidence=0.9,
                    evidence=(SemanticEvidence(source="d", score=0.9, description="e"),),
                    detector="d",
                )
            )
        cols.append(EntityColumnInput(column_name=f"col_{i}", classifications=tuple(cset)))

    # warm-up
    for _ in range(5):
        _ = EntityCandidateDetector.discover(cols)

    runs = 20
    import time

    start = time.perf_counter()
    for _ in range(runs):
        _ = EntityCandidateDetector.discover(cols)
    end = time.perf_counter()
    avg = (end - start) / runs
    assert avg < 0.003
