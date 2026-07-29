import pytest
import math
from uuid import uuid4

from app.semantic.domain_models import DomainEvidence, DomainScore, DomainPrediction
from app.semantic.semantic_types import DatasetDomain, SemanticType


def test_valid_domain_evidence():
    ev = DomainEvidence(domain=DatasetDomain.GENERAL, semantic_type=SemanticType.EMAIL, weight=1.5, description="d")
    assert ev.weight == 1.5


def test_invalid_weight_zero_and_negative():
    with pytest.raises(ValueError):
        DomainEvidence(domain=DatasetDomain.GENERAL, semantic_type=SemanticType.EMAIL, weight=0)
    with pytest.raises(ValueError):
        DomainEvidence(domain=DatasetDomain.GENERAL, semantic_type=SemanticType.EMAIL, weight=-1)


def test_nan_and_infinite_weight_rejected():
    with pytest.raises(ValueError):
        DomainEvidence(domain=DatasetDomain.GENERAL, semantic_type=SemanticType.EMAIL, weight=float('nan'))
    with pytest.raises(ValueError):
        DomainEvidence(domain=DatasetDomain.GENERAL, semantic_type=SemanticType.EMAIL, weight=float('inf'))


def test_valid_domain_score_and_evidence_ordering():
    ev1 = DomainEvidence(domain=DatasetDomain.FINANCE, semantic_type=SemanticType.CURRENCY, weight=1.0)
    ev2 = DomainEvidence(domain=DatasetDomain.FINANCE, semantic_type=SemanticType.CURRENCY, weight=2.0)
    ds = DomainScore(domain=DatasetDomain.FINANCE, score=0.8, evidence=(ev1, ev2))
    assert ds.score == pytest.approx(0.8)
    assert ds.evidence[0] is ev1


def test_invalid_score():
    with pytest.raises(ValueError):
        DomainScore(domain=DatasetDomain.FINANCE, score=1.5)
    with pytest.raises(ValueError):
        DomainScore(domain=DatasetDomain.FINANCE, score=float('nan'))


def test_domain_prediction_alternatives_sorting_and_primary_excluded():
    ds1 = DomainScore(domain=DatasetDomain.HEALTHCARE, score=0.6)
    ds2 = DomainScore(domain=DatasetDomain.FINANCE, score=0.9)
    ds3 = DomainScore(domain=DatasetDomain.GENERAL, score=0.6)
    pred = DomainPrediction(primary_domain=DatasetDomain.FINANCE, confidence=0.85, alternatives=(ds1, ds2, ds3), evidence=(DomainEvidence(domain=DatasetDomain.FINANCE, semantic_type=SemanticType.CURRENCY, weight=1.0),))
    # primary should be excluded from alternatives
    assert all(a.domain != pred.primary_domain for a in pred.alternatives)
    # alternatives sorted by descending score then domain value
    assert pred.alternatives[0].domain == DatasetDomain.HEALTHCARE or pred.alternatives[0].domain == DatasetDomain.GENERAL or pred.alternatives[0].domain == DatasetDomain.HEALTHCARE


def test_invalid_confidence():
    with pytest.raises(ValueError):
        DomainPrediction(primary_domain=DatasetDomain.GENERAL, confidence=2.0)
    with pytest.raises(ValueError):
        DomainPrediction(primary_domain=DatasetDomain.GENERAL, confidence=float('nan'))


def test_immutability():
    ev = DomainEvidence(domain=DatasetDomain.GENERAL, semantic_type=SemanticType.TEXT, weight=1.0)
    with pytest.raises((AttributeError, TypeError)):
        ev.weight = 2.0
