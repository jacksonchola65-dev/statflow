import pytest
from uuid import uuid4

from app.semantic.semantic_types import DatasetDomain, SemanticType, ColumnRole
from app.semantic.semantic_models import (
    SemanticColumn,
    SemanticEntity,
    SemanticRelationship,
    SemanticProfile,
)


def test_enums_exist_and_have_members():
    assert DatasetDomain.HEALTHCARE.name == "HEALTHCARE"
    assert SemanticType.EMAIL.name == "EMAIL"
    assert ColumnRole.DIMENSION.name == "DIMENSION"


def test_models_are_immutable_and_defaults():
    col = SemanticColumn(name="id", semantic_type=SemanticType.IDENTIFIER, confidence=0.9)
    assert col.name == "id"
    assert col.confidence == 0.9
    with pytest.raises((AttributeError, TypeError)):
        col.name = "other"

    eid = uuid4()
    entity = SemanticEntity(id=eid, name="Person", semantic_type=SemanticType.PERSON)
    assert entity.id == eid
    assert isinstance(entity.columns, tuple)
    with pytest.raises((AttributeError, TypeError)):
        entity.name = "Other"


def test_relationship_and_profile_structures():
    e1 = SemanticEntity(id=uuid4(), name="A", semantic_type=SemanticType.ORGANIZATION)
    e2 = SemanticEntity(id=uuid4(), name="B", semantic_type=SemanticType.ORGANIZATION)
    rel = SemanticRelationship(source_entity_id=e1.id, target_entity_id=e2.id, relationship_type="owns", confidence=0.75)
    profile = SemanticProfile(dataset_domain=DatasetDomain.FINANCE, entities=(e1, e2), relationships=(rel,))
    assert profile.dataset_domain == DatasetDomain.FINANCE
    assert profile.entities[0].name == "A"
    assert profile.relationships[0].relationship_type == "owns"
    with pytest.raises((AttributeError, TypeError)):
        profile.dataset_domain = DatasetDomain.HEALTHCARE
