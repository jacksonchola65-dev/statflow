import math
import pytest

from app.semantic.entity_models import EntityCandidate, EntityKeyCandidate, RelationshipCandidate
from app.semantic.semantic_models import SemanticEvidence
from app.semantic.semantic_types import SemanticType


def ev(src="d", score=0.9, desc="e"):
    return SemanticEvidence(source=src, score=score, description=desc)


def test_valid_entity_candidate_and_dedup():
    ec = EntityCandidate(
        name="  Person ",
        semantic_types=(SemanticType.PERSON, SemanticType.PERSON, SemanticType.TEXT),
        source_columns=(" col1 ", "col1", "col2"),
        confidence=0.85,
        evidence=(ev("d1", 0.8), ev("d2", 0.7)),
    )
    assert ec.name == "Person"
    assert ec.semantic_types == (SemanticType.PERSON, SemanticType.TEXT)
    assert ec.source_columns == ("col1", "col2")
    assert math.isclose(ec.confidence, 0.85)
    assert ec.evidence[0].source == "d1"


def test_invalid_source_column_trim_and_empty():
    with pytest.raises(ValueError):
        EntityCandidate(name="E", semantic_types=(SemanticType.PERSON,), source_columns=("   ",), confidence=0.5)


def test_invalid_confidence_nan_inf():
    with pytest.raises(ValueError):
        EntityCandidate(name="E", semantic_types=(SemanticType.PERSON,), source_columns=("c",), confidence=float("nan"))
    with pytest.raises(ValueError):
        EntityCandidate(name="E", semantic_types=(SemanticType.PERSON,), source_columns=("c",), confidence=float("inf"))


def test_malformed_semantic_type():
    with pytest.raises(TypeError):
        EntityCandidate(name="E", semantic_types=("notatype",), source_columns=("c",), confidence=0.5)


def test_entity_key_candidate_valid_and_invalid_ratios():
    ek = EntityKeyCandidate(entity_name="Ent", column_name="col", semantic_type=SemanticType.IDENTIFIER, confidence=0.9, uniqueness_ratio=0.99, null_ratio=0.01, evidence=(ev(),))
    assert ek.entity_name == "Ent"
    assert math.isclose(ek.uniqueness_ratio, 0.99)

    with pytest.raises(ValueError):
        EntityKeyCandidate(entity_name="Ent", column_name="col", semantic_type=SemanticType.IDENTIFIER, confidence=0.9, uniqueness_ratio=1.5, null_ratio=0.0)
    with pytest.raises(ValueError):
        EntityKeyCandidate(entity_name="Ent", column_name="col", semantic_type=SemanticType.IDENTIFIER, confidence=0.9, uniqueness_ratio=0.5, null_ratio=-0.1)


def test_relationship_candidate_and_invalid_fields():
    rc = RelationshipCandidate(source_entity="A", target_entity="B", source_column="a_id", target_column="b_id", confidence=0.8, relationship_type="fk", evidence=(ev(), ev("x", 0.7)))
    assert rc.source_entity == "A" and rc.target_entity == "B"
    assert rc.relationship_type == "fk"

    with pytest.raises(ValueError):
        RelationshipCandidate(source_entity="", target_entity="B", source_column="a", target_column="b", confidence=0.5, relationship_type="r")
    with pytest.raises(ValueError):
        RelationshipCandidate(source_entity="A", target_entity="B", source_column="", target_column="b", confidence=0.5, relationship_type="r")


def test_evidence_ordering_and_immutability():
    e1 = ev("d1", 0.9)
    e2 = ev("d2", 0.8)
    ec = EntityCandidate(name="X", semantic_types=(SemanticType.PERSON,), source_columns=("c",), confidence=0.5, evidence=(e1, e2))
    assert ec.evidence[0].source == "d1" and ec.evidence[1].source == "d2"
    with pytest.raises((AttributeError, TypeError)):
        ec.name = "Y"


def test_nan_in_ratios_and_confidence_rejected():
    with pytest.raises(ValueError):
        EntityKeyCandidate(entity_name="E", column_name="c", semantic_type=SemanticType.IDENTIFIER, confidence=float('nan'), uniqueness_ratio=0.5, null_ratio=0.0)
    with pytest.raises(ValueError):
        EntityKeyCandidate(entity_name="E", column_name="c", semantic_type=SemanticType.IDENTIFIER, confidence=0.5, uniqueness_ratio=float('inf'), null_ratio=0.0)
