import time

import pytest

from app.semantic.analytics_role_models import (
    AnalyticsRoleProfile,
    DimensionCandidate,
    DimensionType,
    MeasureCandidate,
    Aggregation,
)
from app.semantic.analytics_role_service import AnalyticsRoleService
from app.semantic.semantic_models import SemanticEvidence
from app.semantic.semantic_types import SemanticType


def make_measure(name, semantic_type, aggregation, confidence=0.8):
    return MeasureCandidate(
        name=name,
        semantic_type=semantic_type,
        aggregation=aggregation,
        confidence=confidence,
        cardinality_ratio=0.1,
        null_ratio=0.0,
        evidence=(SemanticEvidence(source="svc", score=confidence),),
    )


def make_dimension(name, semantic_type, dimension_type, confidence=0.8):
    return DimensionCandidate(
        name=name,
        semantic_type=semantic_type,
        dimension_type=dimension_type,
        confidence=confidence,
        cardinality_ratio=0.1,
        null_ratio=0.0,
        evidence=(SemanticEvidence(source="svc", score=confidence),),
    )


def test_empty_profile_returns_empty_analytics_role_profile():
    profile = AnalyticsRoleService.compose((), ())
    assert isinstance(profile, AnalyticsRoleProfile)
    assert profile.measure_candidates == ()
    assert profile.dimension_candidates == ()


def test_measure_only_profile_preserved():
    measures = (
        make_measure("revenue", SemanticType.CURRENCY, Aggregation.SUM),
        make_measure("profit_pct", SemanticType.PERCENTAGE, Aggregation.AVG),
    )
    profile = AnalyticsRoleService.compose(measures, ())
    assert profile.measure_candidates == measures
    assert profile.dimension_candidates == ()


def test_dimension_only_profile_preserved():
    dimensions = (
        make_dimension("country", SemanticType.COUNTRY, DimensionType.GEOGRAPHIC),
        make_dimension("year", SemanticType.YEAR, DimensionType.TEMPORAL),
    )
    profile = AnalyticsRoleService.compose((), dimensions)
    assert profile.measure_candidates == ()
    assert profile.dimension_candidates == dimensions


def test_mixed_profile_preserves_both_candidate_sets():
    measures = (
        make_measure("sales", SemanticType.CURRENCY, Aggregation.SUM),
    )
    dimensions = (
        make_dimension("category", SemanticType.CATEGORY, DimensionType.CATEGORICAL),
    )
    profile = AnalyticsRoleService.compose(measures, dimensions)
    assert profile.measure_candidates == measures
    assert profile.dimension_candidates == dimensions


def test_ordering_preserved_from_detectors():
    measures = (
        make_measure("b", SemanticType.INTEGER, Aggregation.SUM),
        make_measure("a", SemanticType.CURRENCY, Aggregation.SUM),
    )
    dimensions = (
        make_dimension("x", SemanticType.CATEGORY, DimensionType.CATEGORICAL),
        make_dimension("y", SemanticType.CITY, DimensionType.GEOGRAPHIC),
    )
    profile = AnalyticsRoleService.compose(measures, dimensions)
    assert profile.measure_candidates == measures
    assert profile.dimension_candidates == dimensions


def test_malformed_measure_rejected():
    with pytest.raises(TypeError):
        AnalyticsRoleService.compose((object(),), ())


def test_malformed_dimension_rejected():
    with pytest.raises(TypeError):
        AnalyticsRoleService.compose((), (object(),))


def test_input_immutability_preserved():
    measures = (make_measure("revenue", SemanticType.CURRENCY, Aggregation.SUM),)
    dimensions = (make_dimension("country", SemanticType.COUNTRY, DimensionType.GEOGRAPHIC),)
    original_measures = measures
    original_dimensions = dimensions
    profile = AnalyticsRoleService.compose(measures, dimensions)
    assert measures == original_measures
    assert dimensions == original_dimensions
    assert profile.measure_candidates == original_measures
    assert profile.dimension_candidates == original_dimensions


def test_determinism_returns_same_profile_for_same_inputs():
    measures = (make_measure("revenue", SemanticType.CURRENCY, Aggregation.SUM),)
    dimensions = (make_dimension("country", SemanticType.COUNTRY, DimensionType.GEOGRAPHIC),)
    first = AnalyticsRoleService.compose(measures, dimensions)
    second = AnalyticsRoleService.compose(measures, dimensions)
    assert first == second


def test_analytics_role_service_performance():
    measures = tuple(
        make_measure(f"m{i}", SemanticType.INTEGER, Aggregation.SUM, confidence=0.8)
        for i in range(100)
    )
    dimensions = tuple(
        make_dimension(f"d{i}", SemanticType.CATEGORY, DimensionType.CATEGORICAL, confidence=0.8)
        for i in range(100)
    )

    for _ in range(5):
        AnalyticsRoleService.compose(measures, dimensions)

    runs = 20
    total = 0.0
    for _ in range(runs):
        start = time.perf_counter()
        AnalyticsRoleService.compose(measures, dimensions)
        total += time.perf_counter() - start

    average = total / runs
    assert average < 0.001
