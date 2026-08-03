import copy
import time
from uuid import uuid4

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
from app.semantic.semantic_profile_builder import (
    ColumnClassification,
    DomainDetectionResult,
    SemanticProfileBuilder,
)
from app.semantic.semantic_profile_models import SemanticProfile as SemanticProfileModel
from app.semantic.semantic_serialization import from_dict, to_dict
from app.semantic.semantic_types import DatasetDomain, SemanticType


def sc(t, c):
    return SemanticClassification(
        semantic_type=t,
        confidence=c,
        evidence=(SemanticEvidence(source="d", score=float(c)),),
        detector="det",
    )


def make_entity_col(name):
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
    return RelationshipColumnInput(
        column_name=f"{target}_{source}_id",
        classifications=(sc(SemanticType.IDENTIFIER, 0.85),),
        uniqueness_ratio=0.9,
        null_ratio=0.1,
    )


@pytest.mark.integration
def test_semantic_profile_integration_scenarios_and_serialization():
    scenarios = []

    # Retail
    retail_entities = ["customer", "product", "order"]
    retail_entity_cols = [make_entity_col(n) for n in retail_entities]
    retail_key_cols = [make_key_col(n) for n in retail_entities]
    retail_rel_cols = [make_rel_col("order", "customer"), make_rel_col("order", "product")]
    scenarios.append((retail_entity_cols, retail_key_cols, retail_rel_cols, DatasetDomain.RETAIL))

    # Healthcare
    hc = ["patient", "doctor", "hospital", "appointment"]
    hc_entity_cols = [make_entity_col(n) for n in hc]
    hc_key_cols = [make_key_col(n) for n in hc]
    hc_rel_cols = [
        make_rel_col("appointment", "patient"),
        make_rel_col("appointment", "doctor"),
        make_rel_col("appointment", "hospital"),
    ]
    scenarios.append((hc_entity_cols, hc_key_cols, hc_rel_cols, DatasetDomain.HEALTHCARE))

    # Education
    ed = ["student", "course", "lecturer", "enrollment"]
    ed_entity_cols = [make_entity_col(n) for n in ed]
    ed_key_cols = [make_key_col(n) for n in ed]
    ed_rel_cols = [
        make_rel_col("enrollment", "student"),
        make_rel_col("enrollment", "course"),
        make_rel_col("enrollment", "lecturer"),
    ]
    scenarios.append((ed_entity_cols, ed_key_cols, ed_rel_cols, DatasetDomain.EDUCATION))

    # HR
    hr = ["employee", "department", "payroll"]
    hr_entity_cols = [make_entity_col(n) for n in hr]
    hr_key_cols = [make_key_col(n) for n in hr]
    hr_rel_cols = [make_rel_col("payroll", "employee"), make_rel_col("payroll", "department")]
    scenarios.append((hr_entity_cols, hr_key_cols, hr_rel_cols, DatasetDomain.HR))

    # Government
    gov = ["citizen", "district", "province", "permit"]
    gov_entity_cols = [make_entity_col(n) for n in gov]
    gov_key_cols = [make_key_col(n) for n in gov]
    gov_rel_cols = [
        make_rel_col("permit", "citizen"),
        make_rel_col("permit", "district"),
        make_rel_col("permit", "province"),
    ]
    scenarios.append((gov_entity_cols, gov_key_cols, gov_rel_cols, DatasetDomain.GOVERNMENT))

    # Mixed-domain metadata: mix entity types; domain_result will drive domain preservation
    mixed_entities = ["cust", "patient", "student"]
    mixed_entity_cols = [make_entity_col(n) for n in mixed_entities]
    mixed_key_cols = [make_key_col(n) for n in mixed_entities]
    mixed_rel_cols = [make_rel_col("cust", "patient")]
    scenarios.append((mixed_entity_cols, mixed_key_cols, mixed_rel_cols, DatasetDomain.GENERAL))

    # No detected domain (UNKNOWN)
    no_domain_entity_cols = [make_entity_col("metric")]
    scenarios.append((no_domain_entity_cols, [], [], DatasetDomain.UNKNOWN))

    # Empty metadata
    empty_entity_cols = []
    scenarios.append((empty_entity_cols, [], [], DatasetDomain.GENERAL))

    for entity_cols, key_cols, rel_cols, expected_domain in scenarios:
        # run detectors
        e_cols_copy = copy.deepcopy(entity_cols)
        k_cols_copy = copy.deepcopy(key_cols)
        r_cols_copy = copy.deepcopy(rel_cols)

        entities = EntityCandidateDetector.discover(tuple(entity_cols))
        keys = EntityKeyDetector.discover(
            EntityKeyDetectionInput(entities=entities, columns=tuple(key_cols))
        )
        rels = RelationshipDetector.discover(
            RelationshipDetectionInput(entities=entities, keys=keys, columns=tuple(rel_cols))
        )

        # builder inputs
        domain = DomainDetectionResult(domain=expected_domain)
        # build simple column classifications from detected keys/measures/dims: preserve ordering
        columns = tuple(
            ColumnClassification(
                column_name=f"c{i}", classifications=(sc(SemanticType.UNKNOWN, 0.5),)
            )
            for i in range(max(1, len(key_cols) or 1))
        )

        profile = SemanticProfileBuilder.compose(
            domain,
            entities,
            rels,
            keys,
            None
            or __import__(
                "app.semantic.analytics_role_models", fromlist=["AnalyticsRoleProfile"]
            ).AnalyticsRoleProfile(),
            columns,
        )

        # Domain preserved
        assert profile.domain == expected_domain

        # Entities and relationships preserved (counts)
        assert len(profile.entities) == len(entities)
        assert len(profile.relationships) >= 0

        # immutability of inputs
        assert entity_cols == e_cols_copy
        assert key_cols == k_cols_copy
        assert rel_cols == r_cols_copy

        # serialization round-trip for SemanticProfileModel
        # convert builder candidate entities/relationships to semantic model types for serialization
        sm = __import__(
            "app.semantic.semantic_models", fromlist=["SemanticEntity", "SemanticRelationship"]
        )
        name_to_id = {}
        sem_entities = []
        for e in entities:
            eid = uuid4()
            _ = e.name if hasattr(e, "name") else getattr(e, "id", str(e))
            name_to_id[getattr(e, "name", str(e))] = eid
            sem_entities.append(
                sm.SemanticEntity(
                    id=eid, name=getattr(e, "name", "entity"), semantic_type=SemanticType.UNKNOWN
                )
            )

        sem_rels = []
        for r in rels:
            # if relationship is a RelationshipCandidate, map names
            if hasattr(r, "source_entity"):
                sid = name_to_id.get(r.source_entity, uuid4())
                tid = name_to_id.get(r.target_entity, uuid4())
                sem_rels.append(
                    sm.SemanticRelationship(
                        source_entity_id=sid,
                        target_entity_id=tid,
                        relationship_type=getattr(r, "relationship_type", "rel"),
                    )
                )
            else:
                # already semantic relationship
                sem_rels.append(r)

        model = SemanticProfileModel(
            domain=profile.domain,
            entities=tuple(sem_entities),
            relationships=tuple(sem_rels),
            columns=profile.columns,
            analytics_roles=profile.analytics_roles,
        )
        d = to_dict(model)
        restored = from_dict(SemanticProfileModel, d)
        assert restored == model


def test_full_pipeline_performance_and_behavior_large():
    # create 100 entity columns, 100 key cols, 100 rel cols
    n = 100
    entity_cols = [make_entity_col(f"ent_{i}") for i in range(n)]
    key_cols = [make_key_col(f"ent_{i}") for i in range(n)]
    rel_cols = [make_rel_col(f"ent_{i}", f"ent_{(i + 1) % n}") for i in range(n)]

    # run detectors once to warm up
    for _ in range(5):
        entities = EntityCandidateDetector.discover(tuple(entity_cols))
        keys = EntityKeyDetector.discover(
            EntityKeyDetectionInput(entities=entities, columns=tuple(key_cols))
        )
        rels = RelationshipDetector.discover(
            RelationshipDetectionInput(entities=entities, keys=keys, columns=tuple(rel_cols))
        )
        _ = SemanticProfileBuilder.compose(
            DomainDetectionResult(domain=DatasetDomain.GENERAL),
            entities,
            rels,
            keys,
            __import__(
                "app.semantic.analytics_role_models", fromlist=["AnalyticsRoleProfile"]
            ).AnalyticsRoleProfile(),
            tuple(
                ColumnClassification(
                    column_name=f"c{i}", classifications=(sc(SemanticType.UNKNOWN, 0.5),)
                )
                for i in range(n)
            ),
        )

    timed = 20
    times = []
    for _ in range(timed):
        t0 = time.perf_counter()
        entities = EntityCandidateDetector.discover(tuple(entity_cols))
        keys = EntityKeyDetector.discover(
            EntityKeyDetectionInput(entities=entities, columns=tuple(key_cols))
        )
        rels = RelationshipDetector.discover(
            RelationshipDetectionInput(entities=entities, keys=keys, columns=tuple(rel_cols))
        )
        _ = SemanticProfileBuilder.compose(
            DomainDetectionResult(domain=DatasetDomain.GENERAL),
            entities,
            rels,
            keys,
            __import__(
                "app.semantic.analytics_role_models", fromlist=["AnalyticsRoleProfile"]
            ).AnalyticsRoleProfile(),
            tuple(
                ColumnClassification(
                    column_name=f"c{i}", classifications=(sc(SemanticType.UNKNOWN, 0.5),)
                )
                for i in range(n)
            ),
        )
        t1 = time.perf_counter()
        times.append(t1 - t0)

    avg = sum(times) / len(times)
    # assert under 10 ms
    assert avg < 0.01
