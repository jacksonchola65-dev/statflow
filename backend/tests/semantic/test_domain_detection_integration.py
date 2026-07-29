import copy
import time
import pytest

from app.semantic.semantic_models import SemanticClassification, SemanticEvidence
from app.semantic.semantic_types import SemanticType, DatasetDomain
from app.semantic.domain_scoring_engine import DomainScoringEngine
from app.semantic.dataset_domain_detector import DatasetDomainDetector
from app.semantic.domain_signatures import DOMAIN_SIGNATURES


def sc(t: SemanticType, c: float = 0.9):
    return SemanticClassification(semantic_type=t, confidence=c, evidence=(SemanticEvidence(source="t", score=float(c), description="e"),), detector="d")


def all_domains():
    return tuple({s.domain for s in DOMAIN_SIGNATURES})


def run_flow(columns):
    cols_copy = copy.deepcopy(columns)
    scores = DomainScoringEngine.score(cols_copy)
    pred = DatasetDomainDetector.predict(scores)
    return scores, pred


def test_healthcare_dataset():
    # columns across multiple columns
    cols = [
        [sc(SemanticType.PERSON, 1.0)],
        [sc(SemanticType.AGE, 0.98)],
        [sc(SemanticType.AGE, 0.99)],
        [sc(SemanticType.IDENTIFIER, 0.97)],
        [sc(SemanticType.DATE, 0.96)],
           [sc(SemanticType.CATEGORY, 0.95)],
           [sc(SemanticType.CATEGORY, 0.99)],
    ]
    scores, pred = run_flow(cols)
    assert pred.primary_domain == DatasetDomain.HEALTHCARE or pred.primary_domain == DatasetDomain.CUSTOM
    assert pred.confidence >= 0.25
    # evidence from at least 2 semantic types and 2 columns
    hc_score = [s for s in scores if s.domain == DatasetDomain.HEALTHCARE][0]
    assert len(hc_score.evidence) >= 2


def test_finance_dataset():
    cols = [
        [sc(SemanticType.CURRENCY, 0.95)],
        [sc(SemanticType.PERCENTAGE, 0.9)],
        [sc(SemanticType.IDENTIFIER, 0.85)],
        [sc(SemanticType.DATE, 0.8)],
        [sc(SemanticType.ORGANIZATION, 0.7)],
    ]
    scores, pred = run_flow(cols)
    assert pred.primary_domain == DatasetDomain.FINANCE
    assert pred.confidence >= 0.25


def test_clear_education_and_ambiguous_case():
    # clear education
    cols_clear = [
        [sc(SemanticType.PERSON, 1.0)],
        [sc(SemanticType.AGE, 0.6)],
        [sc(SemanticType.IDENTIFIER, 0.95)],
        [sc(SemanticType.DATE, 0.9)],
            [sc(SemanticType.CATEGORY, 1.0)],
            [sc(SemanticType.CATEGORY, 1.0)],
    ]
    scores, pred = run_flow(cols_clear)
    assert pred.primary_domain == DatasetDomain.EDUCATION or pred.primary_domain == DatasetDomain.CUSTOM

    # ambiguous healthcare/education: make their scores within 0.09
    cols_amb = [
        [sc(SemanticType.PERSON, 0.9)],
        [sc(SemanticType.AGE, 0.86)],
        [sc(SemanticType.IDENTIFIER, 0.7)],
        [sc(SemanticType.DATE, 0.5)],
    ]
    scores2, pred2 = run_flow(cols_amb)
    # ambiguous should return CUSTOM
    # either healthcare or education could be top; rule enforces CUSTOM when diff < 0.10
    assert pred2.primary_domain == DatasetDomain.CUSTOM


def test_agriculture_dataset():
    cols = [
        [sc(SemanticType.QUANTITY, 0.95)],
        [sc(SemanticType.DATE, 0.9)],
        [sc(SemanticType.PROVINCE, 0.85)],
        [sc(SemanticType.DISTRICT, 0.8)],
        [sc(SemanticType.CATEGORY, 0.7)],
    ]
    scores, pred = run_flow(cols)
    assert pred.primary_domain == DatasetDomain.AGRICULTURE


def test_retail_dataset():
    cols = [
        [sc(SemanticType.CURRENCY, 0.95)],
        [sc(SemanticType.QUANTITY, 0.9)],
        [sc(SemanticType.CATEGORY, 0.85)],
        [sc(SemanticType.DATE, 0.8)],
        [sc(SemanticType.IDENTIFIER, 0.75)],
    ]
    scores, pred = run_flow(cols)
    assert pred.primary_domain == DatasetDomain.RETAIL


def test_hr_dataset():
    cols = [
        [sc(SemanticType.PERSON, 0.95)],
        [sc(SemanticType.ORGANIZATION, 0.9)],
        [sc(SemanticType.AGE, 0.85)],
        [sc(SemanticType.DATE, 0.8)],
        [sc(SemanticType.CURRENCY, 0.75)],
        [sc(SemanticType.IDENTIFIER, 0.7)],
    ]
    scores, pred = run_flow(cols)
    assert pred.primary_domain == DatasetDomain.HR


def test_weak_evidence_dataset():
    # only one meaningful semantic type across multiple columns
    cols = [[sc(SemanticType.AGE, 0.9)], [sc(SemanticType.AGE, 0.85)], [sc(SemanticType.AGE, 0.8)]]
    scores, pred = run_flow(cols)
    assert pred.primary_domain == DatasetDomain.CUSTOM
    assert pred.confidence == 0.0


def test_single_column_protection():
    # multiple classifications but single column
    cols = [[sc(SemanticType.PERSON, 0.9), sc(SemanticType.AGE, 0.85), sc(SemanticType.IDENTIFIER, 0.8)]]
    scores, pred = run_flow(cols)
    # all domain scores must be zero
    assert all(s.score == 0.0 for s in scores)
    assert pred.primary_domain == DatasetDomain.CUSTOM


def test_low_confidence_dataset():
    cols = [
        [sc(SemanticType.PERSON, 0.2)],
        [sc(SemanticType.AGE, 0.15)],
    ]
    scores, pred = run_flow(cols)
    assert pred.primary_domain == DatasetDomain.CUSTOM
    # confidence equals highest positive domain score
    highest_domain_score = max((s.score for s in scores if s.score > 0.0), default=0.0)
    assert pytest.approx(pred.confidence, rel=1e-6) == highest_domain_score


def test_ambiguous_multi_domain_dataset():
    cols = [
        [sc(SemanticType.PERSON, 0.8)],
        [sc(SemanticType.ORGANIZATION, 0.75)],
        [sc(SemanticType.AGE, 0.78)],
    ]
    scores, pred = run_flow(cols)
    # top two domains should be within 0.10 -> ambiguous
    assert pred.primary_domain == DatasetDomain.CUSTOM
    assert len(pred.alternatives) >= 2


def test_empty_dataset():
    scores, pred = run_flow([])
    assert all(s.score == 0.0 for s in scores)
    assert pred.primary_domain == DatasetDomain.CUSTOM and pred.confidence == 0.0 and pred.alternatives == () and pred.evidence == ()


def test_determinism_and_input_immutability():
    cols = [
        [sc(SemanticType.PERSON, 0.9)],
        [sc(SemanticType.AGE, 0.85)],
        [sc(SemanticType.IDENTIFIER, 0.8)],
    ]
    cols_copy = copy.deepcopy(cols)
    s1, p1 = run_flow(cols)
    s2, p2 = run_flow(cols)
    assert s1 == s2 and p1 == p2
    # input not mutated
    assert cols == cols_copy


def test_performance_complete_flow():
    # 100 columns, up to 3 classifications per column
    types = [SemanticType.AGE, SemanticType.PERSON, SemanticType.DATE]
    cols = []
    for i in range(100):
        cset = []
        for j in range((i % 3) + 1):
            cset.append(sc(types[(i + j) % len(types)], 0.8 + 0.05 * j))
        cols.append(cset)

    # warm-up
    for _ in range(5):
        _ = DatasetDomainDetector.predict(DomainScoringEngine.score(cols))

    runs = 20
    total = 0.0
    for _ in range(runs):
        t0 = time.perf_counter()
        _ = DatasetDomainDetector.predict(DomainScoringEngine.score(cols))
        total += time.perf_counter() - t0

    average = total / runs
    # average under 6 ms
    assert average < 0.006
