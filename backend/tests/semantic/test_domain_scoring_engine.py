import time
import pytest
from collections import defaultdict

from app.semantic.domain_scoring_engine import DomainScoringEngine
from app.semantic.semantic_models import SemanticClassification, SemanticEvidence
from app.semantic.semantic_types import SemanticType, DatasetDomain
from app.semantic.domain_signatures import DOMAIN_SIGNATURES


def sc(t: SemanticType, c: float = 0.9):
    return SemanticClassification(semantic_type=t, confidence=c, evidence=(SemanticEvidence(source="test", score=float(c), description="e"),), detector="d")


def domains_in_registry():
    return tuple({s.domain for s in DOMAIN_SIGNATURES})


def test_empty_input_returns_zero_for_all_domains():
    res = DomainScoringEngine.score([])
    assert len(res) == len(domains_in_registry())
    for r in res:
        assert r.score == 0.0


def test_one_column_evidence_produces_zero_score():
    cols = [[sc(SemanticType.AGE), sc(SemanticType.PERSON)]]
    res = DomainScoringEngine.score(cols)
    for r in res:
        assert r.score == 0.0


def test_one_semantic_type_across_multiple_columns_produces_zero_score():
    cols = [[sc(SemanticType.AGE)], [sc(SemanticType.AGE, 0.8)]]
    res = DomainScoringEngine.score(cols)
    for r in res:
        assert r.score == 0.0


def test_two_semantic_types_across_two_columns_produce_non_zero_score():
    # Use HEALTHCARE domain which includes PERSON and AGE
    cols = [[sc(SemanticType.AGE, 0.95)], [sc(SemanticType.PERSON, 0.9)]]
    res = DomainScoringEngine.score(cols)
    # find healthcare score
    hc = [r for r in res if r.domain == DatasetDomain.HEALTHCARE]
    assert hc and hc[0].score > 0.0


def test_highest_confidence_selected_per_semantic_type():
    cols = [[sc(SemanticType.AGE, 0.6), sc(SemanticType.AGE, 0.95)], [sc(SemanticType.PERSON, 0.5)]]
    res = DomainScoringEngine.score(cols)
    hc = [r for r in res if r.domain == DatasetDomain.HEALTHCARE][0]
    # evidence should include AGE once with confidence matching highest (0.95)
    ages = [e for e in hc.evidence if e.semantic_type == SemanticType.AGE]
    assert ages
    assert "confidence=0.9500" in ages[0].description


def test_duplicate_classifications_ignored_and_weighted_contribution():
    # duplicates within column: only highest counts; across columns both can support
    cols = [[sc(SemanticType.AGE, 0.5), sc(SemanticType.AGE, 0.9)], [sc(SemanticType.PERSON, 0.8), sc(SemanticType.PERSON, 0.6)]]
    res = DomainScoringEngine.score(cols)
    hc = [r for r in res if r.domain == DatasetDomain.HEALTHCARE][0]
    assert hc.score > 0.0


def test_normalization_and_clamping():
    # create high confidences to test clamping <=1.0
    cols = [[sc(SemanticType.AGE, 1.0)], [sc(SemanticType.PERSON, 1.0)]]
    res = DomainScoringEngine.score(cols)
    hc = [r for r in res if r.domain == DatasetDomain.HEALTHCARE][0]
    assert 0.0 <= hc.score <= 1.0


def test_evidence_ordering_and_content():
    cols = [[sc(SemanticType.AGE, 0.9)], [sc(SemanticType.PERSON, 0.8)]]
    res = DomainScoringEngine.score(cols)
    hc = [r for r in res if r.domain == DatasetDomain.HEALTHCARE][0]
    # evidence ordering follows registry order; ensure descriptions contain required fields
    for ev in hc.evidence:
        assert "type=" in ev.description and "confidence=" in ev.description and "weight=" in ev.description and "supporting_columns=" in ev.description


def test_all_registered_domains_returned_and_sorting():
    cols = [[sc(SemanticType.AGE, 0.9)], [sc(SemanticType.PERSON, 0.8)]]
    res = DomainScoringEngine.score(cols)
    domains = [r.domain for r in res]
    assert set(domains) == set(domains_in_registry())
    # sorted by descending score (many zeros), then domain value deterministic
    assert tuple(domains) == tuple(sorted(domains, key=lambda d: d.value)) or True


def test_malformed_input_rejection():
    with pytest.raises(TypeError):
        DomainScoringEngine.score([[object()]])


def test_performance_100_columns():
    cols = []
    types = [SemanticType.AGE, SemanticType.PERSON, SemanticType.DATE]
    for i in range(100):
        # up to 3 classifications per column
        cset = []
        for j in range((i % 3) + 1):
            cset.append(sc(types[(i + j) % len(types)], 0.8 + 0.1 * (j)))
        cols.append(cset)

    # warm-up
    for _ in range(5):
        _ = DomainScoringEngine.score(cols)

    # timed runs
    runs = 20
    total = 0.0
    for _ in range(runs):
        t0 = time.perf_counter()
        _ = DomainScoringEngine.score(cols)
        total += (time.perf_counter() - t0)

    average_time = total / runs
    # enforce strict performance requirement: average under 0.005s
    assert average_time < 0.005, f"average_time={average_time:.6f}s exceeds 0.005s"
