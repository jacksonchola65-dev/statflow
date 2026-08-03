import dataclasses

import pytest
from app.semantic.v2.feature_models import ColumnFeatureContext, LightValueFeatures
from app.semantic.v2.semantic_context import DictionaryIndex, RegexIndex, SemanticContext


def make_col(name: str, values):
    # values is tuple[LightValueFeatures]
    non_null = len(values)
    nulls = 0
    unique = len({v.cleaned_value for v in values})
    return ColumnFeatureContext(
        column_name=name,
        values=tuple(values),
        null_count=nulls,
        non_null_count=non_null,
        unique_count=unique,
        cardinality_ratio=(unique / non_null if non_null > 0 else 0.0),
        null_ratio=(nulls / (nulls + non_null) if (nulls + non_null) > 0 else 0.0),
    )


def test_empty_context():
    ctx = SemanticContext(columns=())
    assert ctx.column_count == 0
    assert ctx.total_values == 0
    assert ctx.total_nulls == 0
    assert ctx.total_non_nulls == 0
    with pytest.raises(IndexError):
        ctx.get_column(0)
    with pytest.raises(KeyError):
        ctx.get_column_by_name("x")


def test_single_column_and_lookup():
    v = LightValueFeatures(
        raw_value="a",
        cleaned_value="a",
        lowered_value="a",
        is_empty=False,
        is_integer=False,
        is_decimal=False,
        parsed_number=None,
    )
    col = make_col("c1", (v,))
    ctx = SemanticContext(columns=(col,))
    assert ctx.column_count == 1
    assert ctx.get_column(0) is col
    assert ctx.get_column_by_name("c1") is col


def test_multiple_columns_and_ordering():
    v1 = LightValueFeatures(
        raw_value="a",
        cleaned_value="a",
        lowered_value="a",
        is_empty=False,
        is_integer=False,
        is_decimal=False,
        parsed_number=None,
    )
    v2 = LightValueFeatures(
        raw_value="b",
        cleaned_value="b",
        lowered_value="b",
        is_empty=False,
        is_integer=False,
        is_decimal=False,
        parsed_number=None,
    )
    c1 = make_col("one", (v1,))
    c2 = make_col("two", (v2,))
    ctx = SemanticContext(
        columns=(c1, c2),
        regex_index=RegexIndex(patterns=("p",)),
        dictionary_index=DictionaryIndex(entries=("e",)),
    )
    assert ctx.get_column_by_name("two").column_name == "two"
    assert ctx.columns[0].column_name == "one"
    assert ctx.column_count == 2
    assert ctx.regex_index.patterns == ("p",)
    assert ctx.dictionary_index.entries == ("e",)


def test_duplicate_name_rejected():
    v = LightValueFeatures(
        raw_value="a",
        cleaned_value="a",
        lowered_value="a",
        is_empty=False,
        is_integer=False,
        is_decimal=False,
        parsed_number=None,
    )
    c1 = make_col("dup", (v,))
    c2 = make_col("dup", (v,))
    with pytest.raises(ValueError):
        SemanticContext(columns=(c1, c2))


def test_immutability_and_determinism():
    v = LightValueFeatures(
        raw_value="a",
        cleaned_value="a",
        lowered_value="a",
        is_empty=False,
        is_integer=False,
        is_decimal=False,
        parsed_number=None,
    )
    c = make_col("x", (v,))
    ctx1 = SemanticContext(columns=(c,))
    ctx2 = SemanticContext(columns=(c,))
    assert ctx1 == ctx2
    with pytest.raises(dataclasses.FrozenInstanceError):
        ctx1.column_count = 5
