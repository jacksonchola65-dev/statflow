from uuid import uuid4

import pytest
from app.semantic.analytics_role_models import (
    Aggregation,
    AnalyticsRoleProfile,
    DimensionCandidate,
    DimensionType,
    MeasureCandidate,
)
from app.semantic.entity_models import EntityKeyCandidate
from app.semantic.semantic_models import (
    SemanticClassification,
    SemanticColumn,
    SemanticEntity,
    SemanticEvidence,
    SemanticProfile,
    SemanticRelationship,
    SemanticSuggestion,
)
from app.semantic.semantic_profile_models import SemanticColumnProfile
from app.semantic.semantic_profile_models import SemanticProfile as SemanticProfileModel
from app.semantic.semantic_serialization import from_dict, to_dict
from app.semantic.semantic_types import ColumnRole, DatasetDomain, SemanticType


def test_round_trip_classification_and_profile():
    col = SemanticColumn(
        name="age", semantic_type=SemanticType.AGE, role=ColumnRole.ATTRIBUTE, confidence=0.99
    )
    ev = SemanticEvidence(source="d1", score=0.8, description="match")
    sug = SemanticSuggestion(semantic_type=SemanticType.AGE, confidence=0.8)
    sc = SemanticClassification(
        semantic_type=SemanticType.AGE,
        confidence=0.95,
        evidence=(ev,),
        detector="d1",
        suggestions=(sug,),
    )

    ent = SemanticEntity(
        id=uuid4(), name="Person", semantic_type=SemanticType.PERSON, columns=(col,), confidence=0.9
    )
    rel = SemanticRelationship(
        source_entity_id=ent.id, target_entity_id=ent.id, relationship_type="self", confidence=0.5
    )
    profile = SemanticProfile(
        dataset_domain=DatasetDomain.GENERAL,
        columns=(col,),
        entities=(ent,),
        relationships=(rel,),
        overall_confidence=0.85,
    )

    sc_dict = to_dict(sc)
    sc2 = from_dict(SemanticClassification, sc_dict)
    assert sc == sc2

    p_dict = to_dict(profile)
    p2 = from_dict(SemanticProfile, p_dict)
    assert profile == p2


def test_enum_serialization_and_invalid_enum():
    col = SemanticColumn(
        name="email", semantic_type=SemanticType.EMAIL, role=ColumnRole.IDENTIFIER, confidence=0.5
    )
    d = to_dict(col)
    assert d["semantic_type"] == "EMAIL"
    assert d["role"] == "IDENTIFIER"

    bad = d.copy()
    bad["semantic_type"] = "NO_SUCH"
    with pytest.raises(ValueError):
        from_dict(SemanticColumn, bad)


def test_missing_fields_and_invalid_confidence():
    with pytest.raises(KeyError):
        from_dict(
            SemanticColumn, {"role": "IDENTIFIER", "semantic_type": "EMAIL", "confidence": 0.1}
        )

    bad_conf = {"name": "x", "semantic_type": "TEXT", "role": "ATTRIBUTE", "confidence": 2.0}
    with pytest.raises(ValueError):
        from_dict(SemanticColumn, bad_conf)


def test_tuple_ordering_preserved():
    e1 = SemanticEvidence(source="a", score=0.1)
    e2 = SemanticEvidence(source="b", score=0.2)
    sc = SemanticClassification(semantic_type=SemanticType.TEXT, confidence=0.5, evidence=(e1, e2))
    d = to_dict(sc)
    sc2 = from_dict(SemanticClassification, d)
    assert sc2.evidence[0].source == "a"


def test_semantic_column_profile_serialization_deterministic():
    col_profile = SemanticColumnProfile(
        column_name="x",
        classifications=(SemanticClassification(semantic_type=SemanticType.TEXT, confidence=0.7),),
        key_candidates=(
            EntityKeyCandidate(
                entity_name="Person",
                column_name="id",
                semantic_type=SemanticType.IDENTIFIER,
                confidence=0.9,
                uniqueness_ratio=0.95,
                null_ratio=0.0,
                evidence=(SemanticEvidence(source="t", score=0.9),),
            ),
        ),
        measure_candidates=(
            MeasureCandidate(
                name="count",
                semantic_type=SemanticType.INTEGER,
                aggregation=Aggregation.SUM,
                confidence=0.8,
                cardinality_ratio=0.1,
                null_ratio=0.0,
                evidence=(SemanticEvidence(source="t", score=0.8),),
            ),
        ),
        dimension_candidates=(
            DimensionCandidate(
                name="category",
                semantic_type=SemanticType.CATEGORY,
                dimension_type=DimensionType.CATEGORICAL,
                confidence=0.85,
                cardinality_ratio=0.2,
                null_ratio=0.0,
                evidence=(SemanticEvidence(source="t", score=0.85),),
            ),
        ),
    )
    original = to_dict(col_profile)
    copy = to_dict(col_profile)
    assert original == copy
    assert original["classifications"][0]["semantic_type"] == "TEXT"
    assert original["key_candidates"][0]["semantic_type"] == "IDENTIFIER"
    assert original["measure_candidates"][0]["aggregation"] == "SUM"
    assert original["dimension_candidates"][0]["dimension_type"] == "CATEGORICAL"
    assert col_profile.column_name == "x"


def test_semantic_profile_model_serialization_deterministic():
    col_profile = SemanticColumnProfile(column_name="x")
    profile = SemanticProfileModel(
        domain=DatasetDomain.GENERAL,
        entities=(SemanticEntity(id=uuid4(), name="Person", semantic_type=SemanticType.PERSON),),
        relationships=(
            SemanticRelationship(
                source_entity_id=uuid4(),
                target_entity_id=uuid4(),
                relationship_type="self",
                confidence=0.5,
            ),
        ),
        columns=(col_profile,),
        analytics_roles=AnalyticsRoleProfile(),
    )
    original = to_dict(profile)
    copy = to_dict(profile)
    assert original == copy
    assert original["domain"] == "GENERAL"
    assert isinstance(original["columns"], list)
    assert original["analytics_roles"]["measure_candidates"] == []
    assert profile.columns == (col_profile,)


def test_empty_semantic_profile_serialization():
    profile = SemanticProfileModel(domain=DatasetDomain.GENERAL)
    serialized = to_dict(profile)
    assert serialized == {
        "domain": "GENERAL",
        "entities": [],
        "relationships": [],
        "columns": [],
        "analytics_roles": {"measure_candidates": [], "dimension_candidates": []},
    }
    assert profile.entities == ()
    assert profile.columns == ()


def test_serialization_does_not_mutate_models():
    col_profile = SemanticColumnProfile(column_name="x")
    profile = SemanticProfileModel(domain=DatasetDomain.GENERAL, columns=(col_profile,))
    _ = to_dict(profile)
    assert profile.columns == (col_profile,)
    assert col_profile.classifications == ()
