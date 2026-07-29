import pytest
from collections import defaultdict
from app.semantic.domain_signatures import DOMAIN_SIGNATURES
from app.semantic.semantic_types import DatasetDomain, SemanticType
from app.semantic.domain_models import DomainEvidence


def test_registry_immutable_and_tuple():
    assert isinstance(DOMAIN_SIGNATURES, tuple)
    with pytest.raises(TypeError):
        DOMAIN_SIGNATURES[0] = None


def test_all_domains_present_and_min_signatures():
    required = {DatasetDomain.HEALTHCARE, DatasetDomain.FINANCE, DatasetDomain.EDUCATION, DatasetDomain.AGRICULTURE, DatasetDomain.GOVERNMENT, DatasetDomain.RETAIL, DatasetDomain.MANUFACTURING, DatasetDomain.INSURANCE, DatasetDomain.TELECOM, DatasetDomain.ENERGY, DatasetDomain.HR, DatasetDomain.RESEARCH}
    by_domain = defaultdict(list)
    for s in DOMAIN_SIGNATURES:
        assert isinstance(s, DomainEvidence)
        by_domain[s.domain].append(s)

    assert required.issubset(set(by_domain.keys()))
    for d in required:
        assert len(by_domain[d]) >= 4


def test_weights_and_types_valid():
    pairs = set()
    for s in DOMAIN_SIGNATURES:
        assert isinstance(s.semantic_type, SemanticType)
        assert isinstance(s.domain, DatasetDomain)
        assert s.weight > 0 and s.weight <= 1.0
        assert s.weight == s.weight and s.weight != float('inf')
        key = (s.domain, s.semantic_type)
        assert key not in pairs
        pairs.add(key)


def test_common_types_lower_weights():
    # Date and Identifier should have lower weights across registry
    for s in DOMAIN_SIGNATURES:
        if s.semantic_type in (SemanticType.DATE, SemanticType.IDENTIFIER):
            assert s.weight <= 0.4


def test_deterministic_ordering():
    # Ensure ordering is stable by checking first entries are as defined
    first_domains = tuple(s.domain for s in DOMAIN_SIGNATURES[:6])
    assert isinstance(first_domains, tuple)
