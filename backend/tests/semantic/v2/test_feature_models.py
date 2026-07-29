import dataclasses
import pytest
from app.semantic.v2.feature_models import LightValueFeatures, ColumnFeatureContext, ExtendedValueFeatures


def make_value(raw: str, parsed: float | None = None):
    return LightValueFeatures(
        raw_value=raw,
        cleaned_value=raw.strip(),
        lowered_value=raw.strip().lower(),
        is_empty=(raw.strip() == ""),
        is_integer=False,
        is_decimal=False,
        parsed_number=(float(parsed) if parsed is not None else None),
    )


def test_valid_value_feature():
    v = make_value(" Hello123 ")
    assert v.raw_value == " Hello123 "
    assert v.cleaned_value == "Hello123"
    # extended features derived deterministically
    ext = ExtendedValueFeatures.from_light(v)
    assert isinstance(ext.tokens, tuple)


def test_valid_column_context():
    v1 = make_value("a")
    v2 = make_value("b")
    ctx = ColumnFeatureContext(
        column_name="col",
        values=(v1, v2),
        null_count=0,
        non_null_count=2,
        unique_count=2,
        cardinality_ratio=1.0,
        null_ratio=0.0,
    )
    assert ctx.column_name == "col"
    assert ctx.non_null_count == 2


def test_empty_column_context():
    ctx = ColumnFeatureContext(
        column_name="empty",
        values=(),
        null_count=0,
        non_null_count=0,
        unique_count=0,
        cardinality_ratio=0.0,
        null_ratio=0.0,
    )
    assert ctx.values == ()


def test_immutability():
    v = make_value("x")
    ctx = ColumnFeatureContext(
        column_name="c",
        values=(v,),
        null_count=0,
        non_null_count=1,
        unique_count=1,
        cardinality_ratio=1.0,
        null_ratio=0.0,
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        ctx.column_name = "changed"


def test_tuple_enforcement_and_ordering():
    v1 = make_value("first")
    v2 = make_value("second")
    ctx = ColumnFeatureContext(
        column_name="o",
        values=(v1, v2),
        null_count=0,
        non_null_count=2,
        unique_count=2,
        cardinality_ratio=1.0,
        null_ratio=0.0,
    )
    assert isinstance(ctx.values, tuple)
    assert ctx.values[0].raw_value == "first"


def test_invalid_ratios():
    v = make_value("x")
    with pytest.raises(ValueError):
        ColumnFeatureContext(
            column_name="bad",
            values=(v,),
            null_count=0,
            non_null_count=1,
            unique_count=1,
            cardinality_ratio=1.5,
            null_ratio=0.0,
        )


def test_invalid_counts():
    v = make_value("x")
    with pytest.raises(ValueError):
        ColumnFeatureContext(
            column_name="bad",
            values=(v,),
            null_count=-1,
            non_null_count=1,
            unique_count=1,
            cardinality_ratio=1.0,
            null_ratio=0.0,
        )


def test_invalid_nested_values():
    with pytest.raises(TypeError):
        ColumnFeatureContext(
            column_name="bad",
            values=("not a feature",),
            null_count=0,
            non_null_count=1,
            unique_count=1,
            cardinality_ratio=1.0,
            null_ratio=0.0,
        )


def test_count_consistency():
    v = make_value("x")
    with pytest.raises(ValueError):
        ColumnFeatureContext(
            column_name="bad",
            values=(v,),
            null_count=0,
            non_null_count=2,
            unique_count=1,
            cardinality_ratio=0.5,
            null_ratio=0.0,
        )


def test_equality_and_serialization():
    v1 = make_value("a")
    v2 = make_value("b")
    ctx1 = ColumnFeatureContext(
        column_name="c",
        values=(v1, v2),
        null_count=0,
        non_null_count=2,
        unique_count=2,
        cardinality_ratio=1.0,
        null_ratio=0.0,
    )
    ctx2 = ColumnFeatureContext(
        column_name="c",
        values=(v1, v2),
        null_count=0,
        non_null_count=2,
        unique_count=2,
        cardinality_ratio=1.0,
        null_ratio=0.0,
    )
    assert ctx1 == ctx2
    # deterministic serialization using dataclasses.asdict
    d1 = dataclasses.asdict(ctx1)
    d2 = dataclasses.asdict(ctx2)
    assert d1 == d2
