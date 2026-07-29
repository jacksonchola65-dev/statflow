import dataclasses
import random
import time
from typing import Tuple, Optional

import pytest

from app.semantic.v2.feature_extraction import FeatureExtractionPipeline
from app.semantic.v2.feature_models import LightValueFeatures, ExtendedValueFeatures, ColumnFeatureContext


def run_extract(values: Tuple[Optional[str], ...]) -> ColumnFeatureContext:
    return FeatureExtractionPipeline.extract("col", values)


def test_empty_column():
    ctx = run_extract(())
    assert ctx.column_name == "col"
    assert ctx.values == ()
    assert ctx.null_count == 0
    assert ctx.non_null_count == 0
    assert ctx.unique_count == 0
    assert ctx.cardinality_ratio == 0.0
    assert ctx.null_ratio == 0.0


def test_null_handling():
    ctx = run_extract((None, None))
    assert ctx.null_count == 2
    assert ctx.non_null_count == 0
    assert ctx.values == ()


def test_mixed_values_and_ordering():
    vals = (" a ", None, "B", "a")
    ctx = run_extract(vals)
    assert ctx.null_count == 1
    assert ctx.non_null_count == 3
    # ordering preserved for non-nulls
    assert ctx.values[0].raw_value == " a "
    assert ctx.values[1].raw_value == "B"
    assert ctx.values[2].raw_value == "a"


def test_integer_parsing():
    ctx = run_extract(("1", "-2", "003"))
    for v in ctx.values:
        assert v.parsed_number is not None
        assert v.is_integer
        assert not v.is_decimal


def test_decimal_parsing():
    ctx = run_extract(("1.5", "-0.25", "2e3"))
    for v in ctx.values:
        assert v.parsed_number is not None
        assert v.is_decimal


def test_text_values_and_tokenization():
    ctx = run_extract(("Hello World", "foo"))
    v0 = ctx.values[0]
    assert v0.cleaned_value == "Hello World"
    assert v0.lowered_value == "hello world"
    ext = ExtendedValueFeatures.from_light(v0)
    assert isinstance(ext.tokens, tuple)
    assert ext.tokens == ("hello", "world")


def test_statistics_and_uniqueness():
    ctx = run_extract(("a", "b", "a", None))
    assert ctx.null_count == 1
    assert ctx.non_null_count == 3
    assert ctx.unique_count == 2
    assert ctx.cardinality_ratio == pytest.approx(2 / 3)


def test_determinism_and_immutability():
    vals = ("x", "y", None, "x")
    ctx1 = run_extract(vals)
    ctx2 = run_extract(vals)
    assert ctx1 == ctx2
    with pytest.raises(dataclasses.FrozenInstanceError):
        ctx1.column_name = "changed"


def test_invalid_inputs():
    with pytest.raises(TypeError):
        FeatureExtractionPipeline.extract(123, ())
    with pytest.raises(TypeError):
        FeatureExtractionPipeline.extract("c", ["a"])  # not a tuple
    with pytest.raises(TypeError):
        FeatureExtractionPipeline.extract("c", (1,))  # values must be str or None


def test_performance_benchmark():
    # 1,000 values, mixed
    N = 1000
    choices = [None] + [str(i) for i in range(100)] + ["hello world", "foo bar baz"]
    sample = tuple(random.choice(choices) for _ in range(N))
    # warm-up
    for _ in range(5):
        FeatureExtractionPipeline.extract("col", sample)

    times = []
    for _ in range(20):
        t0 = time.perf_counter()
        FeatureExtractionPipeline.extract("col", sample)
        t1 = time.perf_counter()
        times.append(t1 - t0)

    avg = sum(times) / len(times)
    # record avg for human inspection; do not enforce hard fail here
    assert avg < 0.5  # generous upper bound to avoid flaky CI
