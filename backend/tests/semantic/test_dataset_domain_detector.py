import pytest
from app.semantic.dataset_domain_detector import DatasetDomainDetector
from app.semantic.domain_models import DomainScore
from app.semantic.semantic_types import DatasetDomain


def ds(domain, score, evidence=()):
    return DomainScore(domain=domain, score=score, evidence=evidence)


def test_malformed_input_rejected():
    with pytest.raises(TypeError):
        DatasetDomainDetector.predict([object()])


def test_empty_input_returns_custom():
    p = DatasetDomainDetector.predict([])
    assert (
        p.primary_domain == DatasetDomain.CUSTOM
        and p.confidence == 0.0
        and p.alternatives == ()
        and p.evidence == ()
    )


def test_all_zero_scores_returns_custom():
    scores = [ds(DatasetDomain.HEALTHCARE, 0.0), ds(DatasetDomain.FINANCE, 0.0)]
    p = DatasetDomainDetector.predict(scores)
    assert p.primary_domain == DatasetDomain.CUSTOM and p.confidence == 0.0


def test_clear_primary_domain_and_confidence_and_evidence():
    scores = [ds(DatasetDomain.HEALTHCARE, 0.9, evidence=("e",)), ds(DatasetDomain.FINANCE, 0.2)]
    p = DatasetDomainDetector.predict(scores)
    assert p.primary_domain == DatasetDomain.HEALTHCARE
    assert p.confidence == 0.9
    assert p.evidence == ("e",)


def test_alternatives_exclude_primary_and_limited_to_three():
    # create 5 positive domains
    scores = [
        ds(DatasetDomain.HEALTHCARE, 0.9),
        ds(DatasetDomain.FINANCE, 0.5),
        ds(DatasetDomain.EDUCATION, 0.4),
        ds(DatasetDomain.RETAIL, 0.3),
        ds(DatasetDomain.INSURANCE, 0.2),
    ]
    p = DatasetDomainDetector.predict(scores)
    assert p.primary_domain == DatasetDomain.HEALTHCARE
    assert len(p.alternatives) <= 3
    assert all(a.domain != p.primary_domain for a in p.alternatives)


def test_ambiguity_fallback():
    # top two within 0.1 -> ambiguous
    scores = [
        ds(DatasetDomain.HEALTHCARE, 0.5, evidence=("e1",)),
        ds(DatasetDomain.FINANCE, 0.45, evidence=("e2",)),
    ]
    p = DatasetDomainDetector.predict(scores)
    assert p.primary_domain == DatasetDomain.CUSTOM
    assert p.confidence == 0.5
    assert p.evidence == ("e1",)


def test_minimum_confidence_fallback():
    scores = [ds(DatasetDomain.HEALTHCARE, 0.24, evidence=("e1",)), ds(DatasetDomain.FINANCE, 0.1)]
    p = DatasetDomainDetector.predict(scores)
    assert p.primary_domain == DatasetDomain.CUSTOM
    assert p.confidence == 0.24


def test_exact_tie_results_in_custom():
    scores = [
        ds(DatasetDomain.HEALTHCARE, 0.5, evidence=("e1",)),
        ds(DatasetDomain.FINANCE, 0.5, evidence=("e2",)),
    ]
    p = DatasetDomainDetector.predict(scores)
    assert p.primary_domain == DatasetDomain.CUSTOM


def test_input_ordering_ignored_and_deterministic():
    a = ds(DatasetDomain.FINANCE, 0.6)
    b = ds(DatasetDomain.HEALTHCARE, 0.9)
    p1 = DatasetDomainDetector.predict([a, b])
    p2 = DatasetDomainDetector.predict([b, a])
    assert p1.primary_domain == p2.primary_domain and p1.confidence == p2.confidence


def test_immutability_preserved():
    s = ds(DatasetDomain.HEALTHCARE, 0.9, evidence=("e",))
    _ = DatasetDomainDetector.predict([s])
    # prediction should not alter original DomainScore
    assert s.score == 0.9


def test_performance_100_scores():
    # create 100 DomainScore inputs with varying positive/zero
    scores = []
    domains = [
        DatasetDomain.HEALTHCARE,
        DatasetDomain.FINANCE,
        DatasetDomain.EDUCATION,
        DatasetDomain.RETAIL,
        DatasetDomain.INSURANCE,
        DatasetDomain.GOVERNMENT,
    ]
    for i in range(100):
        d = domains[i % len(domains)]
        sc = 0.1 + (i % 5) * 0.2
        scores.append(ds(d, sc))

    # warm-up
    for _ in range(5):
        _ = DatasetDomainDetector.predict(scores)

    runs = 20
    import time

    start = time.perf_counter()
    for _ in range(runs):
        _ = DatasetDomainDetector.predict(scores)
    end = time.perf_counter()
    avg = (end - start) / runs
    assert avg < 0.001, f"average prediction time {avg:.6f}s exceeds 1ms"
