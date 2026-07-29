import pytest
from uuid import uuid4

from app.semantic.analytics_role_models import AnalyticsRoleProfile, Aggregation, DimensionCandidate, DimensionType, MeasureCandidate
from app.semantic.entity_models import EntityKeyCandidate
from app.semantic.semantic_models import (
    SemanticClassification,
    SemanticEntity,
    SemanticEvidence,
    SemanticRelationship,
)
from app.semantic.semantic_profile_models import SemanticColumnProfile, SemanticProfile
from app.semantic.semantic_types import DatasetDomain, SemanticType


def make_classification(semantic_type, confidence=0.8):
    return SemanticClassification(
        semantic_type=semantic_type,
        confidence=confidence,
        evidence=(SemanticEvidence(source="t", score=confidence),),
    )


def make_measure(name):
    return MeasureCandidate(
        name=name,
        semantic_type=SemanticType.INTEGER,
        aggregation=Aggregation.SUM,
        confidence=0.8,
        cardinality_ratio=0.1,
        null_ratio=0.0,
        evidence=(SemanticEvidence(source="t", score=0.8),),
    )


def make_dimension(name):
    return DimensionCandidate(
        name=name,
        semantic_type=SemanticType.CATEGORY,
        dimension_type=DimensionType.CATEGORICAL,
        confidence=0.8,
        cardinality_ratio=0.1,
        null_ratio=0.0,
        evidence=(SemanticEvidence(source="t", score=0.8),),
    )


def make_key_candidate():
    return EntityKeyCandidate(
        entity_name="Person",
        column_name="id",
        semantic_type=SemanticType.IDENTIFIER,
        confidence=0.9,
        uniqueness_ratio=0.95,
        null_ratio=0.0,
        evidence=(SemanticEvidence(source="t", score=0.9),),
    )


def test_valid_complete_profile():
    col = SemanticColumnProfile(
        column_name="age",
        classifications=(make_classification(SemanticType.AGE),),
        key_candidates=(make_key_candidate(),),
        measure_candidates=(make_measure("age"),),
        dimension_candidates=(make_dimension("age_dim"),),
    )
    entity = SemanticEntity(
        id=uuid4(),
        name="Person",
        semantic_type=SemanticType.PERSON,
        columns=(col,),
        confidence=0.9,
    )
    relation = SemanticRelationship(
        source_entity_id=entity.id,
        target_entity_id=entity.id,
        relationship_type="self",
        confidence=0.5,
    )
    roles = AnalyticsRoleProfile(measure_candidates=(make_measure("age"),), dimension_candidates=(make_dimension("age_dim"),))
    profile = SemanticProfile(
        domain=DatasetDomain.GENERAL,
        entities=(entity,),
        relationships=(relation,),
        columns=(col,),
        analytics_roles=roles,
    )

    assert profile.domain == DatasetDomain.GENERAL
    assert profile.entities == (entity,)
    assert profile.relationships == (relation,)
    assert profile.columns == (col,)
    assert profile.analytics_roles == roles


def test_empty_profile():
    profile = SemanticProfile(domain=DatasetDomain.GENERAL)
    assert profile.entities == ()
    assert profile.relationships == ()
    assert profile.columns == ()
    assert profile.analytics_roles == AnalyticsRoleProfile()


def test_nested_validation_rejects_invalid_column_profile():
    with pytest.raises(TypeError):
        SemanticProfile(domain=DatasetDomain.GENERAL, columns=(object(),))


def test_immutability():
    col = SemanticColumnProfile(column_name="x")
    with pytest.raises(AttributeError):
        col.column_name = "y"


def test_tuple_enforcement():
    col = SemanticColumnProfile(column_name="x")
    assert isinstance(col.classifications, tuple)
    assert isinstance(col.key_candidates, tuple)
    assert isinstance(col.measure_candidates, tuple)
    assert isinstance(col.dimension_candidates, tuple)


def test_ordering_preserved():
    col = SemanticColumnProfile(
        column_name="x",
        classifications=(make_classification(SemanticType.TEXT), make_classification(SemanticType.EMAIL)),
    )
    assert [c.semantic_type for c in col.classifications] == [SemanticType.TEXT, SemanticType.EMAIL]


def test_equality():
    col1 = SemanticColumnProfile(column_name="x")
    col2 = SemanticColumnProfile(column_name="x")
    assert col1 == col2


def test_serialization_via_repr_and_equality():
    col = SemanticColumnProfile(column_name="x", classifications=(make_classification(SemanticType.TEXT),))
    serialized = repr(col)
    assert "SemanticColumnProfile" in serialized
    assert "column_name='x'" in serialized


def test_malformed_input_rejected():
    with pytest.raises(TypeError):
        SemanticColumnProfile(column_name="x", classifications=(object(),))
    with pytest.raises(TypeError):
        SemanticColumnProfile(column_name="x", key_candidates=(object(),))
    with pytest.raises(TypeError):
        SemanticColumnProfile(column_name="x", measure_candidates=(object(),))
    with pytest.raises(TypeError):
        SemanticColumnProfile(column_name="x", dimension_candidates=(object(),))
    with pytest.raises(TypeError):
        SemanticProfile(domain=DatasetDomain.GENERAL, entities=(object(),))
    with pytest.raises(TypeError):
        SemanticProfile(domain=DatasetDomain.GENERAL, relationships=(object(),))
    with pytest.raises(TypeError):
        SemanticProfile(domain=DatasetDomain.GENERAL, columns=(object(),))
    with pytest.raises(TypeError):
        SemanticProfile(domain=DatasetDomain.GENERAL, analytics_roles=object())
