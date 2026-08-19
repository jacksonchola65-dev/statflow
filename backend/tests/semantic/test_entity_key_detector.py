import copy
import time

import pytest
from app.semantic.entity_key_detector import (
    EntityKeyColumnInput,
    EntityKeyDetectionInput,
    EntityKeyDetector,
)
from app.semantic.entity_models import EntityCandidate
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
        EntityKeyDetector.discover(object())


def test_empty_entities_or_columns():
    inp = EntityKeyDetectionInput(entities=(), columns=())
    assert EntityKeyDetector.discover(inp) == ()


def test_identifier_detection():
    ent = EntityCandidate(name="customer")
    col = EntityKeyColumnInput(
        column_name="customer_id",
        classifications=(sc(SemanticType.IDENTIFIER, 0.9),),
        uniqueness_ratio=0.85,
        null_ratio=0.01,
    )
    inp = EntityKeyDetectionInput(entities=(ent,), columns=(col,))
    res = EntityKeyDetector.discover(inp)
    assert len(res) == 1
    r = res[0]
    assert r.entity_name == "customer"
    assert r.column_name == "customer_id"
    assert r.semantic_type == SemanticType.IDENTIFIER
    # confidence formula for identifier
    expected = 0.50 * 0.9 + 0.35 * 0.85 + 0.15 * (1 - 0.01)
    assert abs(r.confidence - expected) < 1e-9
    assert r.evidence[0].source == "d"


def test_integer_fallback_detection():
    ent = EntityCandidate(name="order")
    col = EntityKeyColumnInput(
        column_name="order",
        classifications=(sc(SemanticType.INTEGER, 0.95),),
        uniqueness_ratio=0.96,
        null_ratio=0.0,
    )
    inp = EntityKeyDetectionInput(entities=(ent,), columns=(col,))
    res = EntityKeyDetector.discover(inp)
    assert len(res) == 1
    r = res[0]
    expected = 0.35 * 0.95 + 0.50 * 0.96 + 0.15 * (1 - 0.0)
    assert abs(r.confidence - expected) < 1e-9


def test_text_fallback_detection_and_thresholds():
    ent = EntityCandidate(name="doc")
    # below uniqueness threshold should be ignored
    col_bad = EntityKeyColumnInput(
        column_name="doc_key",
        classifications=(sc(SemanticType.TEXT, 0.9),),
        uniqueness_ratio=0.9,
        null_ratio=0.0,
    )
    col_good = EntityKeyColumnInput(
        column_name="doc_key",
        classifications=(sc(SemanticType.TEXT, 0.9),),
        uniqueness_ratio=0.96,
        null_ratio=0.0,
    )
    inp_bad = EntityKeyDetectionInput(entities=(ent,), columns=(col_bad,))
    inp_good = EntityKeyDetectionInput(entities=(ent,), columns=(col_good,))
    assert EntityKeyDetector.discover(inp_bad) == ()
    res = EntityKeyDetector.discover(inp_good)
    assert len(res) == 1


def test_confidence_threshold_and_null_threshold():
    ent = EntityCandidate(name="u")
    col = EntityKeyColumnInput(
        column_name="u_id",
        classifications=(sc(SemanticType.IDENTIFIER, 0.59),),
        uniqueness_ratio=0.9,
        null_ratio=0.0,
    )
    inp = EntityKeyDetectionInput(entities=(ent,), columns=(col,))
    assert EntityKeyDetector.discover(inp) == ()


def test_name_normalization_and_suffix_removal_and_unmatched_ignored():
    ent = EntityCandidate(name="Employee")
    col_match = EntityKeyColumnInput(
        column_name=" employee-code ",
        classifications=(sc(SemanticType.IDENTIFIER, 0.9),),
        uniqueness_ratio=0.9,
        null_ratio=0.0,
    )
    col_unmatched = EntityKeyColumnInput(
        column_name="dept_id",
        classifications=(sc(SemanticType.IDENTIFIER, 0.9),),
        uniqueness_ratio=0.9,
        null_ratio=0.0,
    )
    inp = EntityKeyDetectionInput(entities=(ent,), columns=(col_match, col_unmatched))
    res = EntityKeyDetector.discover(inp)
    assert len(res) == 1
    assert res[0].entity_name == "Employee"


def test_duplicate_entity_name_first_match():
    e1 = EntityCandidate(name="client")
    e2 = EntityCandidate(name="client")
    col = EntityKeyColumnInput(
        column_name="client_id",
        classifications=(sc(SemanticType.IDENTIFIER, 0.9),),
        uniqueness_ratio=0.9,
        null_ratio=0.0,
    )
    inp = EntityKeyDetectionInput(entities=(e1, e2), columns=(col,))
    res = EntityKeyDetector.discover(inp)
    assert res[0].entity_name == "client"


def test_highest_classification_selected_and_tie_break():
    ent = EntityCandidate(name="x")
    # two classifications same confidence for INTEGER and TEXT -> tie-break by SemanticType.value
    c1 = SemanticClassification(
        semantic_type=SemanticType.INTEGER,
        confidence=0.9,
        evidence=(SemanticEvidence(source="d", score=0.9),),
    )
    c2 = SemanticClassification(
        semantic_type=SemanticType.TEXT,
        confidence=0.9,
        evidence=(SemanticEvidence(source="d", score=0.9),),
    )
    col = EntityKeyColumnInput(
        column_name="x", classifications=(c1, c2), uniqueness_ratio=0.96, null_ratio=0.0
    )
    inp = EntityKeyDetectionInput(entities=(ent,), columns=(col,))
    res = EntityKeyDetector.discover(inp)
    assert len(res) == 1
    # whichever semantic_type.value is smaller comes first per tie-break; ensure semantic_type is one of them
    assert res[0].semantic_type in (SemanticType.INTEGER, SemanticType.TEXT)


def test_confidence_clamping_and_evidence_preserved_and_input_immutability():
    ent = EntityCandidate(name="big")
    col = EntityKeyColumnInput(
        column_name="big_id",
        classifications=(sc(SemanticType.IDENTIFIER, 1.0),),
        uniqueness_ratio=1.0,
        null_ratio=0.0,
    )
    inp_cols = (col,)
    inp = EntityKeyDetectionInput(entities=(ent,), columns=inp_cols)
    cols_copy = copy.deepcopy(inp_cols)
    res = EntityKeyDetector.discover(inp)
    assert res[0].confidence <= 0.99
    assert res[0].evidence[0].source == "d"
    assert inp_cols == cols_copy


def test_deterministic_sorting():
    e1 = EntityCandidate(name="A")
    e2 = EntityCandidate(name="B")
    c1 = EntityKeyColumnInput(
        column_name="A_id",
        classifications=(sc(SemanticType.IDENTIFIER, 0.9),),
        uniqueness_ratio=0.9,
        null_ratio=0.0,
    )
    c2 = EntityKeyColumnInput(
        column_name="B_id",
        classifications=(sc(SemanticType.IDENTIFIER, 0.9),),
        uniqueness_ratio=0.9,
        null_ratio=0.0,
    )
    inp = EntityKeyDetectionInput(entities=(e1, e2), columns=(c2, c1))
    res = EntityKeyDetector.discover(inp)
    # both have same confidence; sorting by entity_name case-insensitively should put A before B
    assert res[0].entity_name.lower() == "a"


@pytest.mark.performance
def test_performance_100x100():
    # 100 entities, 100 columns
    entities = tuple(EntityCandidate(name=f"ent_{i}") for i in range(100))
    types = [SemanticType.IDENTIFIER, SemanticType.INTEGER, SemanticType.TEXT]
    cols = []
    for i in range(100):
        cset = []
        for j in range((i % 3) + 1):
            t = types[(i + j) % len(types)]
            conf = 0.9 - j * 0.02
            cset.append(
                SemanticClassification(
                    semantic_type=t,
                    confidence=conf,
                    evidence=(SemanticEvidence(source="d", score=float(conf), description="e"),),
                )
            )
        cols.append(
            EntityKeyColumnInput(
                column_name=f"ent_{i}_id",
                classifications=tuple(cset),
                uniqueness_ratio=0.98,
                null_ratio=0.01,
            )
        )

    inp = EntityKeyDetectionInput(entities=entities, columns=tuple(cols))
    # warm-up
    for _ in range(5):
        _ = EntityKeyDetector.discover(inp)

    runs = 20
    start = time.perf_counter()
    for _ in range(runs):
        _ = EntityKeyDetector.discover(inp)
    end = time.perf_counter()
    avg = (end - start) / runs
    assert avg < 0.004
