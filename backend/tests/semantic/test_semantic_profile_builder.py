import time
from uuid import uuid4

import pytest

from app.semantic.analytics_role_models import AnalyticsRoleProfile, Aggregation, DimensionCandidate, DimensionType, MeasureCandidate
from app.semantic.entity_models import EntityCandidate, EntityKeyCandidate, RelationshipCandidate
from app.semantic.semantic_models import SemanticClassification, SemanticEvidence
from app.semantic.semantic_profile_builder import ColumnClassification, DomainDetectionResult, SemanticProfileBuilder
from app.semantic.semantic_profile_models import SemanticColumnProfile, SemanticProfile
from app.semantic.semantic_types import DatasetDomain, SemanticType


def make_classification(semantic_type, confidence=0.8):
    return SemanticClassification(
        semantic_type=semantic_type,
        confidence=confidence,
        evidence=(SemanticEvidence(source="t", score=confidence),),
    )


def make_entity():
    return EntityCandidate(name="Person", semantic_types=(SemanticType.PERSON,), source_columns=("id",), confidence=0.9, evidence=(SemanticEvidence(source="t", score=0.9),))


def make_key():
    return EntityKeyCandidate(
        entity_name="Person",
        column_name="id",
        semantic_type=SemanticType.IDENTIFIER,
        confidence=0.9,
        uniqueness_ratio=0.95,
        null_ratio=0.0,
        evidence=(SemanticEvidence(source="t", score=0.9),),
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


def test_complete_profile_assembly():
    domain = DomainDetectionResult(domain=DatasetDomain.GENERAL)
    entity = make_entity()
    relationship = RelationshipCandidate(
        source_entity="Person",
        target_entity="Person",
        source_column="id",
        target_column="id",
        confidence=0.9,
        relationship_type="self",
        evidence=(SemanticEvidence(source="t", score=0.9),),
    )
    key = make_key()
    measure = make_measure("id")
    dimension = make_dimension("id")
    roles = AnalyticsRoleProfile(measure_candidates=(measure,), dimension_candidates=(dimension,))
    columns = (ColumnClassification(column_name="id", classifications=(make_classification(SemanticType.IDENTIFIER),)),)

    profile = SemanticProfileBuilder.compose(domain, (entity,), (relationship,), (key,), roles, columns)

    assert profile.domain == DatasetDomain.GENERAL
    assert profile.entities == (entity,)
    assert profile.relationships == (relationship,)
    assert profile.columns == (SemanticColumnProfile(column_name="id", classifications=(make_classification(SemanticType.IDENTIFIER),), key_candidates=(key,), measure_candidates=(measure,), dimension_candidates=(dimension,),),)
    assert profile.analytics_roles == roles


def test_empty_profile():
    domain = DomainDetectionResult(domain=DatasetDomain.GENERAL)
    profile = SemanticProfileBuilder.compose(domain, (), (), (), AnalyticsRoleProfile(), ())
    assert profile.domain == DatasetDomain.GENERAL
    assert profile.entities == ()
    assert profile.relationships == ()
    assert profile.columns == ()
    assert profile.analytics_roles == AnalyticsRoleProfile()


def test_columns_without_roles():
    domain = DomainDetectionResult(domain=DatasetDomain.GENERAL)
    columns = (
        ColumnClassification(column_name="x", classifications=(make_classification(SemanticType.TEXT),)),
    )
    profile = SemanticProfileBuilder.compose(domain, (), (), (), AnalyticsRoleProfile(), columns)
    assert profile.columns[0].measure_candidates == ()
    assert profile.columns[0].dimension_candidates == ()
    assert profile.columns[0].key_candidates == ()


def test_multiple_keys_on_one_column():
    domain = DomainDetectionResult(domain=DatasetDomain.GENERAL)
    key1 = make_key()
    key2 = EntityKeyCandidate(
        entity_name="Person",
        column_name="id",
        semantic_type=SemanticType.IDENTIFIER,
        confidence=0.85,
        uniqueness_ratio=0.8,
        null_ratio=0.0,
        evidence=(SemanticEvidence(source="t", score=0.85),),
    )
    profile = SemanticProfileBuilder.compose(
        domain,
        (),
        (),
        (key1, key2),
        AnalyticsRoleProfile(),
        (ColumnClassification(column_name="id", classifications=(make_classification(SemanticType.IDENTIFIER),)),),
    )
    assert profile.columns[0].key_candidates == (key1, key2)


def test_measures_and_dimensions_on_same_column():
    domain = DomainDetectionResult(domain=DatasetDomain.GENERAL)
    measure = make_measure("id")
    dimension = make_dimension("id")
    roles = AnalyticsRoleProfile(measure_candidates=(measure,), dimension_candidates=(dimension,))
    profile = SemanticProfileBuilder.compose(
        domain,
        (),
        (),
        (),
        roles,
        (ColumnClassification(column_name="id", classifications=(make_classification(SemanticType.IDENTIFIER),)),),
    )
    assert profile.columns[0].measure_candidates == (measure,)
    assert profile.columns[0].dimension_candidates == (dimension,)


def test_ordering_preserved():
    domain = DomainDetectionResult(domain=DatasetDomain.GENERAL)
    columns = (
        ColumnClassification(column_name="a", classifications=(make_classification(SemanticType.TEXT),)),
        ColumnClassification(column_name="b", classifications=(make_classification(SemanticType.EMAIL),)),
    )
    profile = SemanticProfileBuilder.compose(domain, (), (), (), AnalyticsRoleProfile(), columns)
    assert [c.column_name for c in profile.columns] == ["a", "b"]


def test_nested_validation_rejects_malformed():
    domain = DomainDetectionResult(domain=DatasetDomain.GENERAL)
    with pytest.raises(TypeError):
        SemanticProfileBuilder.compose(domain, (object(),), (), (), AnalyticsRoleProfile(), ())
    with pytest.raises(TypeError):
        SemanticProfileBuilder.compose(domain, (), (object(),), (), AnalyticsRoleProfile(), ())
    with pytest.raises(TypeError):
        SemanticProfileBuilder.compose(domain, (), (), (object(),), AnalyticsRoleProfile(), ())
    with pytest.raises(TypeError):
        SemanticProfileBuilder.compose(domain, (), (), (), AnalyticsRoleProfile(), (object(),))


def test_determinism():
    domain = DomainDetectionResult(domain=DatasetDomain.GENERAL)
    profile1 = SemanticProfileBuilder.compose(domain, (), (), (), AnalyticsRoleProfile(), ())
    profile2 = SemanticProfileBuilder.compose(domain, (), (), (), AnalyticsRoleProfile(), ())
    assert profile1 == profile2


def test_input_immutability():
    domain = DomainDetectionResult(domain=DatasetDomain.GENERAL)
    entities = (make_entity(),)
    relationships = (
        RelationshipCandidate(
            source_entity="Person",
            target_entity="Person",
            source_column="id",
            target_column="id",
            confidence=0.9,
            relationship_type="self",
            evidence=(SemanticEvidence(source="t", score=0.9),),
        ),
    )
    keys = (make_key(),)
    roles = AnalyticsRoleProfile()
    columns = (ColumnClassification(column_name="id", classifications=(make_classification(SemanticType.IDENTIFIER),)),)
    original_entities = entities
    original_relationships = relationships
    original_keys = keys
    original_columns = columns

    profile = SemanticProfileBuilder.compose(domain, entities, relationships, keys, roles, columns)

    assert entities == original_entities
    assert relationships == original_relationships
    assert keys == original_keys
    assert columns == original_columns
    assert profile.entities == entities
    assert profile.relationships == relationships
    assert profile.columns[0].column_name == columns[0].column_name
    assert profile.columns[0].classifications == columns[0].classifications


def test_semantic_profile_builder_performance():
    domain = DomainDetectionResult(domain=DatasetDomain.GENERAL)
    entities = tuple(make_entity() for _ in range(100))
    relationships = tuple(
        RelationshipCandidate(
            source_entity="Person",
            target_entity="Person",
            source_column="id",
            target_column="id",
            confidence=0.9,
            relationship_type="self",
            evidence=(SemanticEvidence(source="t", score=0.9),),
        )
        for _ in range(100)
    )
    keys = tuple(
        EntityKeyCandidate(
            entity_name="Person",
            column_name=f"c{i}",
            semantic_type=SemanticType.IDENTIFIER,
            confidence=0.9,
            uniqueness_ratio=0.95,
            null_ratio=0.0,
            evidence=(SemanticEvidence(source="t", score=0.9),),
        )
        for i in range(100)
    )
    measures = tuple(make_measure(f"c{i}") for i in range(100))
    dimensions = tuple(make_dimension(f"c{i}") for i in range(100))
    roles = AnalyticsRoleProfile(measure_candidates=measures, dimension_candidates=dimensions)
    columns = tuple(ColumnClassification(column_name=f"c{i}", classifications=(make_classification(SemanticType.TEXT),)) for i in range(100))

    for _ in range(5):
        SemanticProfileBuilder.compose(domain, entities, relationships, keys, roles, columns)

    runs = 20
    total = 0.0
    for _ in range(runs):
        start = time.perf_counter()
        SemanticProfileBuilder.compose(domain, entities, relationships, keys, roles, columns)
        total += time.perf_counter() - start

    average = total / runs
    assert average < 0.002
