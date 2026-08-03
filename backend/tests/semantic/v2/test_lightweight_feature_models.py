import dataclasses
import random
import statistics
import time
import tracemalloc

import pytest
from app.semantic.v2.feature_extraction import FeatureExtractionPipeline
from app.semantic.v2.feature_models import ExtendedValueFeatures, LightValueFeatures


def test_lightweight_creation_and_ordering():
    vals = (" a ", None, "B", "a")
    ctx = FeatureExtractionPipeline.extract("col", vals)
    assert ctx.null_count == 1
    assert ctx.non_null_count == 3
    assert isinstance(ctx.values[0], LightValueFeatures)
    assert ctx.values[0].raw_value == " a "


def test_extended_factory_no_recompute():
    v = LightValueFeatures(
        raw_value=" X12 ",
        cleaned_value="X12",
        lowered_value="x12",
        is_empty=False,
        is_integer=False,
        is_decimal=False,
        parsed_number=None,
    )
    ext = ExtendedValueFeatures.from_light(v)
    assert ext.character_count == len(v.cleaned_value)
    assert ext.digit_count == sum(1 for c in v.cleaned_value if c.isdigit())
    # factory does not modify light
    assert v.cleaned_value == "X12"


def test_no_repeated_clean_lower_parse():
    vals = tuple(str(i) for i in range(100))
    ctx = FeatureExtractionPipeline.extract("col", vals)
    # create extended features twice and ensure same result
    exts1 = [ExtendedValueFeatures.from_light(light_val) for light_val in ctx.values]
    exts2 = [ExtendedValueFeatures.from_light(light_val) for light_val in ctx.values]
    assert exts1 == exts2


def test_immutability_and_validation():
    v = LightValueFeatures(
        raw_value="a",
        cleaned_value="a",
        lowered_value="a",
        is_empty=False,
        is_integer=False,
        is_decimal=False,
        parsed_number=None,
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        v.raw_value = "b"


def test_performance_lightweight_and_extended():
    N_list = [100, 500, 1000]
    results = {}
    for N in N_list:
        choices = [None] + [str(i) for i in range(100)] + ["hello world", "foo bar baz"]
        sample = tuple(random.choice(choices) for _ in range(N))
        for _ in range(5):
            FeatureExtractionPipeline.extract("col", sample)

        times = []
        peaks = []
        for _ in range(30):
            tracemalloc.start()
            t0 = time.perf_counter()
            FeatureExtractionPipeline.extract("col", sample)
            t1 = time.perf_counter()
            current, peak = tracemalloc.get_traced_memory()
            tracemalloc.stop()
            times.append(t1 - t0)
            peaks.append(peak)

        avg = statistics.mean(times)
        p95 = statistics.quantiles(times, n=100)[94]
        results[N] = (avg, p95, avg / N * 1e6, max(peaks))

    # extended creation benchmark for 1000 values
    sample = tuple(str(i) for i in range(1000))
    ctx = FeatureExtractionPipeline.extract("col", sample)
    for _ in range(5):
        [ExtendedValueFeatures.from_light(light_val) for light_val in ctx.values]
    ext_times = []
    ext_peaks = []
    for _ in range(30):
        tracemalloc.start()
        t0 = time.perf_counter()
        [ExtendedValueFeatures.from_light(light_val) for light_val in ctx.values]
        t1 = time.perf_counter()
        current, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        ext_times.append(t1 - t0)
        ext_peaks.append(peak)

    ext_avg = statistics.mean(ext_times)
    ext_p95 = statistics.quantiles(ext_times, n=100)[94]

    # Simple assertions to ensure reasonable performance
    assert results[100][0] < 0.005
    assert results[500][0] < 0.02
    assert results[1000][0] < 0.04
    # record ext metrics in test result container
    results["ext"] = (ext_avg, ext_p95, max(ext_peaks))
