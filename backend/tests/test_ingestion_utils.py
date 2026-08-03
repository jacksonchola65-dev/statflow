"""
tests/test_ingestion_utils.py
==============================
Comprehensive unit tests for the pure utility functions in
`app/utils/ingestion_parser.py`.

Completely standalone — no database, no fixtures, no async.

Covers:
  - normalize_column_name
  - normalize_column_names (deduplication)
  - is_missing_value
  - serialize_sample_value
  - infer_column_type
  - profile_column (basic smoke tests)
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

import pytest
from app.models.ingestion import InferredColumnType
from app.utils.ingestion_parser import (
    infer_column_type,
    is_missing_value,
    normalize_column_name,
    normalize_column_names,
    profile_column,
    serialize_sample_value,
)

# ===========================================================================
# Column normalisation tests
# ===========================================================================


def test_normalize_spaces():
    """Spaces become underscores: 'Province Name' → 'province_name'."""
    assert normalize_column_name("Province Name") == "province_name"


def test_normalize_punctuation():
    """Parentheses and digits are handled: 'Total (2022)' → 'total_2022'."""
    assert normalize_column_name("Total (2022)") == "total_2022"


def test_normalize_repeated_separators():
    """Multiple underscores collapse: 'a__b' → 'a_b'."""
    assert normalize_column_name("a__b") == "a_b"


def test_normalize_leading_trailing():
    """Leading/trailing underscores stripped: '__abc__' → 'abc'."""
    assert normalize_column_name("__abc__") == "abc"


def test_normalize_empty_string():
    """Empty string → 'column'."""
    assert normalize_column_name("") == "column"


def test_normalize_punctuation_only():
    """Punctuation-only string → 'column'."""
    assert normalize_column_name("---") == "column"


def test_normalize_none_input():
    """None input → 'column'."""
    assert normalize_column_name(None) == "column"


def test_normalize_numeric_input():
    """Integer input 42 → '42'."""
    assert normalize_column_name(42) == "42"


def test_normalize_is_idempotent():
    """normalize(normalize(x)) == normalize(x) for a variety of inputs."""
    inputs = [
        "Province Name",
        "Total (2022)",
        "a__b",
        "",
        "---",
        None,
        42,
        "GDP Growth %",
        "District/Code",
        "   leading spaces  ",
        "UPPER CASE",
        "already_normalised",
        "123col",
    ]
    for x in inputs:
        once = normalize_column_name(x)
        twice = normalize_column_name(once)
        assert once == twice, f"Idempotent failure for {x!r}: {once!r} → {twice!r}"


def test_normalize_slash():
    """Slash becomes underscore: 'District/Code' → 'district_code'."""
    assert normalize_column_name("District/Code") == "district_code"


def test_normalize_percent():
    """Percent and trailing space stripped: 'GDP Growth %' → 'gdp_growth'."""
    assert normalize_column_name("GDP Growth %") == "gdp_growth"


# ===========================================================================
# Duplicate handling (normalize_column_names) tests
# ===========================================================================


def test_dedup_case_collisions():
    """Different-case forms of the same name deduplicate correctly."""
    result = normalize_column_names(["Value", "value", "VALUE"])
    assert result == ["value", "value_2", "value_3"]


def test_dedup_punctuation_collisions():
    """Punctuation-only inputs all normalise to 'column' and get suffixes."""
    result = normalize_column_names(["", "---", "column"])
    assert result == ["column", "column_2", "column_3"]


def test_dedup_existing_suffix_collision():
    """When suffix candidate already exists, counter keeps incrementing.

    ["Value", "Value 2", "Value"] →
      "value"        (first)
      "value_2"      (from "Value 2")
      "value_3"      (third "Value" can't use _2, bumps to _3)
    """
    result = normalize_column_names(["Value", "Value 2", "Value"])
    assert len(result) == 3
    # All three must be unique
    assert len(set(result)) == 3
    # First is plain base
    assert result[0] == "value"
    # Second is value_2 (from "Value 2")
    assert result[1] == "value_2"
    # Third must be something other than value_2 (was already taken)
    assert result[2] != "value_2"
    assert result[2].startswith("value_")


def test_dedup_no_duplicates():
    """No duplicates → names pass through unchanged."""
    result = normalize_column_names(["a", "b", "c"])
    assert result == ["a", "b", "c"]


def test_dedup_preserves_order():
    """Output order matches input order."""
    names = ["Zebra", "Apple", "Mango", "apple"]
    result = normalize_column_names(names)
    # First three are distinct after normalisation
    assert result[0] == "zebra"
    assert result[1] == "apple"
    assert result[2] == "mango"
    # Fourth collides with second
    assert result[3] == "apple_2"


# ===========================================================================
# Missing value (is_missing_value) tests
# ===========================================================================


def test_missing_none():
    assert is_missing_value(None) is True


def test_missing_empty_string():
    assert is_missing_value("") is True


def test_missing_whitespace():
    assert is_missing_value("  ") is True


def test_missing_whitespace_tabs():
    assert is_missing_value("\t\n ") is True


def test_missing_nan_float():
    assert is_missing_value(float("nan")) is True


def test_not_missing_zero():
    assert is_missing_value(0) is False


def test_not_missing_zero_float():
    assert is_missing_value(0.0) is False


def test_not_missing_false():
    assert is_missing_value(False) is False


def test_not_missing_zero_string():
    assert is_missing_value("0") is False


def test_not_missing_false_string():
    assert is_missing_value("false") is False


def test_not_missing_regular_string():
    assert is_missing_value("hello") is False


def test_not_missing_nonzero_int():
    assert is_missing_value(42) is False


# ===========================================================================
# Sample serialisation (serialize_sample_value) tests
# ===========================================================================


def test_serialize_string():
    assert serialize_sample_value("hello") == "hello"


def test_serialize_long_string_truncated():
    long_str = "x" * 300
    result = serialize_sample_value(long_str)
    assert isinstance(result, str)
    assert len(result) == 200


def test_serialize_integer():
    assert serialize_sample_value(42) == 42
    assert isinstance(serialize_sample_value(42), int)


def test_serialize_float():
    assert serialize_sample_value(3.14) == 3.14


def test_serialize_bool_true():
    result = serialize_sample_value(True)
    assert result is True
    assert isinstance(result, bool)


def test_serialize_bool_false():
    result = serialize_sample_value(False)
    # False is a missing value, so should return None
    # Wait — False is NOT a missing value per spec (is_missing_value(False) == False)
    # serialize_sample_value checks is_missing_value first, then isinstance(value, bool)
    # is_missing_value(False) → False, so we reach bool check → return False as-is
    assert result is False
    assert isinstance(result, bool)


def test_serialize_bool_not_confused_with_int():
    """True serialises as bool True, not int 1."""
    result = serialize_sample_value(True)
    assert result is True
    assert type(result) is bool


def test_serialize_date():
    assert serialize_sample_value(date(2024, 1, 15)) == "2024-01-15"


def test_serialize_datetime():
    result = serialize_sample_value(datetime(2024, 1, 15, 12, 0, 0))
    assert result == "2024-01-15T12:00:00"


def test_serialize_decimal():
    """Decimal serialises as its exact string representation."""
    assert serialize_sample_value(Decimal("12.50")) == "12.50"


def test_serialize_decimal_preserves_precision():
    assert serialize_sample_value(Decimal("0.001")) == "0.001"


def test_serialize_missing_none():
    assert serialize_sample_value(None) is None


def test_serialize_nan():
    assert serialize_sample_value(float("nan")) is None


def test_serialize_inf():
    assert serialize_sample_value(float("inf")) is None


def test_serialize_neg_inf():
    assert serialize_sample_value(float("-inf")) is None


def test_serialize_unsupported_object():
    """An arbitrary object should return a string, never raise."""

    class MyObj:
        def __str__(self):
            return "my_obj_repr"

    result = serialize_sample_value(MyObj())
    assert isinstance(result, str)
    assert result == "my_obj_repr"


def test_serialize_never_raises():
    """serialize_sample_value must never raise even on edge-case inputs."""
    tricky_inputs = [object(), [1, 2, 3], {"a": 1}, b"bytes", complex(1, 2)]
    for v in tricky_inputs:
        try:
            serialize_sample_value(v)  # must not raise
        except Exception as exc:  # noqa: BLE001
            pytest.fail(f"serialize_sample_value raised for {v!r}: {exc}")


# ===========================================================================
# Type inference — INTEGER
# ===========================================================================


def test_infer_integer_objects():
    assert infer_column_type([1, 2, 3]) == InferredColumnType.INTEGER


def test_infer_integer_strings():
    assert infer_column_type(["1", "2", "3"]) == InferredColumnType.INTEGER


def test_infer_signed_integer():
    assert infer_column_type(["-5", "0", "100"]) == InferredColumnType.INTEGER


def test_infer_zero_string():
    assert infer_column_type(["0"]) == InferredColumnType.INTEGER


def test_infer_large_integer():
    assert infer_column_type(["999999999", "-1000000"]) == InferredColumnType.INTEGER


# ===========================================================================
# Type inference — DECIMAL
# ===========================================================================


def test_infer_decimal_objects():
    assert infer_column_type([Decimal("1.5")]) == InferredColumnType.DECIMAL


def test_infer_decimal_strings():
    assert infer_column_type(["1.5", "2.0"]) == InferredColumnType.DECIMAL


def test_infer_scientific_notation():
    """Scientific notation infers DECIMAL (documented behaviour).

    Values like '1.5e10' pass Decimal() and contain 'e', so they resolve to DECIMAL.
    """
    assert infer_column_type(["1.5e10", "2.3E-4"]) == InferredColumnType.DECIMAL


def test_infer_negative_decimal():
    assert infer_column_type(["-1.5"]) == InferredColumnType.DECIMAL


# ===========================================================================
# Type inference — BOOLEAN
# ===========================================================================


def test_infer_bool_python_objects():
    """Python True/False objects always infer BOOLEAN."""
    assert infer_column_type([True, False, True]) == InferredColumnType.BOOLEAN


def test_infer_bool_text_true_false():
    """'true'/'false' (case-insensitive) → BOOLEAN."""
    assert infer_column_type(["true", "false", "True"]) == InferredColumnType.BOOLEAN


def test_infer_bool_text_yes_no():
    """'yes'/'no' (case-insensitive) → BOOLEAN."""
    assert infer_column_type(["yes", "no", "Yes"]) == InferredColumnType.BOOLEAN


def test_infer_integer_not_boolean():
    """'1' and '0' must NOT infer BOOLEAN — they are integers."""
    assert infer_column_type(["1", "0"]) == InferredColumnType.INTEGER


def test_infer_one_not_boolean():
    """Python 1 and 0 (non-bool ints) → INTEGER, not BOOLEAN."""
    # int(1) and int(0) are not bool
    result = infer_column_type([1, 0])
    assert result == InferredColumnType.INTEGER


def test_infer_y_n_not_boolean():
    """'y'/'n' are not in the boolean set → TEXT."""
    assert infer_column_type(["y", "n"]) == InferredColumnType.TEXT


def test_infer_on_off_not_boolean():
    """'on'/'off' are not in the boolean set → TEXT."""
    assert infer_column_type(["on", "off"]) == InferredColumnType.TEXT


def test_infer_tf_not_boolean():
    """'t'/'f' are not in the boolean set → TEXT."""
    assert infer_column_type(["t", "f"]) == InferredColumnType.TEXT


# ===========================================================================
# Type inference — DATE
# ===========================================================================


def test_infer_date_objects():
    assert infer_column_type([date(2024, 1, 1)]) == InferredColumnType.DATE


def test_infer_date_iso():
    assert infer_column_type(["2024-01-15"]) == InferredColumnType.DATE


def test_infer_date_slash_format():
    """YYYY/MM/DD with consistent separator → DATE."""
    assert infer_column_type(["2024/01/15"]) == InferredColumnType.DATE


def test_infer_ambiguous_date_stays_text():
    """Ambiguous MM/DD/YYYY format → TEXT."""
    assert infer_column_type(["01/02/2025"]) == InferredColumnType.TEXT


def test_infer_date_ddmmyy_stays_text():
    """Short 2-digit year format DD-MM-YY → TEXT."""
    assert infer_column_type(["02-03-24"]) == InferredColumnType.TEXT


def test_infer_date_mixed_separator_stays_text():
    """Mixed separators (YYYY-MM/DD) → TEXT (not a valid date format)."""
    assert infer_column_type(["2024-01/15"]) == InferredColumnType.TEXT


# ===========================================================================
# Type inference — DATETIME
# ===========================================================================


def test_infer_datetime_objects():
    assert infer_column_type([datetime(2024, 1, 1, 12, 0)]) == InferredColumnType.DATETIME


def test_infer_datetime_iso():
    assert infer_column_type(["2024-01-15T12:00:00"]) == InferredColumnType.DATETIME


def test_infer_datetime_not_downgraded():
    """datetime objects must infer DATETIME, not DATE."""
    assert infer_column_type([datetime(2024, 1, 1, 12, 0)]) != InferredColumnType.DATE


def test_infer_datetime_with_timezone():
    assert infer_column_type(["2024-01-15T12:00:00Z"]) == InferredColumnType.DATETIME


def test_infer_datetime_with_space_separator():
    """YYYY-MM-DD HH:MM:SS (space separator) → DATETIME."""
    assert infer_column_type(["2024-01-15 12:00:00"]) == InferredColumnType.DATETIME


# ===========================================================================
# Type inference — TEXT and edge cases
# ===========================================================================


def test_infer_leading_zero_text():
    """'00123' has leading zero → TEXT."""
    assert infer_column_type(["00123"]) == InferredColumnType.TEXT


def test_infer_currency_text():
    """Currency symbols → TEXT."""
    assert infer_column_type(["K1,250", "$12.50"]) == InferredColumnType.TEXT


def test_infer_mixed_types_text():
    """Mix of integer, text, date → TEXT."""
    assert infer_column_type(["1", "hello", "2024-01-01"]) == InferredColumnType.TEXT


def test_infer_all_missing_text():
    """All missing values → TEXT."""
    assert infer_column_type([None, "", "  "]) == InferredColumnType.TEXT


def test_infer_nan_treated_as_missing():
    """float('nan') is treated as missing → all missing → TEXT."""
    assert infer_column_type([float("nan")]) == InferredColumnType.TEXT


def test_infer_infinity_text():
    """Infinity strings → TEXT (not DECIMAL)."""
    assert infer_column_type(["inf", "-inf"]) == InferredColumnType.TEXT


def test_infer_positive_infinity_string_text():
    assert infer_column_type(["infinity"]) == InferredColumnType.TEXT


def test_infer_comma_number_text():
    """Comma-separated numbers stay TEXT."""
    assert infer_column_type(["1,000", "2,500"]) == InferredColumnType.TEXT


def test_infer_values_not_mutated():
    """The original list must be unchanged after infer_column_type is called."""
    original = ["1", "2", "3", None, ""]
    copy = list(original)
    infer_column_type(original)
    assert original == copy


def test_infer_mixed_date_and_datetime_text():
    """A column with both DATE and DATETIME strings → TEXT (mixed → TEXT)."""
    assert infer_column_type(["2024-01-01", "2024-01-01T12:00:00"]) == InferredColumnType.TEXT


def test_infer_empty_list():
    """Empty list → TEXT."""
    assert infer_column_type([]) == InferredColumnType.TEXT


def test_infer_single_none():
    assert infer_column_type([None]) == InferredColumnType.TEXT


def test_infer_mixed_missing_and_integers():
    """Missing values are ignored; remaining integers → INTEGER."""
    assert infer_column_type([None, "", "  ", "42", "7"]) == InferredColumnType.INTEGER


def test_infer_mixed_missing_and_booleans():
    """Missing values ignored; remaining 'true'/'false' → BOOLEAN."""
    assert infer_column_type([None, "true", "", "false"]) == InferredColumnType.BOOLEAN


# ===========================================================================
# profile_column smoke tests
# ===========================================================================


def test_profile_all_present():
    prof = profile_column("Score", "score", ["10", "20", "30", "40", "50"])
    assert prof.missing_count == 0
    assert prof.nullable is False
    assert prof.unique_count == 5
    assert prof.inferred_type == InferredColumnType.INTEGER


def test_profile_some_missing():
    prof = profile_column("Score", "score", ["10", "", None, "20"])
    assert prof.missing_count == 2
    assert prof.nullable is True
    assert prof.inferred_type == InferredColumnType.INTEGER


def test_profile_all_missing():
    prof = profile_column("Empty", "empty", [None, "", "  "])
    assert prof.missing_count == 3
    assert prof.nullable is True
    assert prof.inferred_type == InferredColumnType.TEXT
    assert prof.sample_values == []


def test_profile_sample_capped_at_5():
    """More than 5 distinct values — sample is capped at 5."""
    values = [str(i) for i in range(20)]
    prof = profile_column("ID", "id", values)
    assert len(prof.sample_values) == 5


def test_profile_sample_distinct_only():
    """Duplicate values are counted once in sample_values."""
    values = ["a", "a", "a", "b", "b", "c"]
    prof = profile_column("Tag", "tag", values)
    assert len(prof.sample_values) == 3
    assert "a" in prof.sample_values
    assert "b" in prof.sample_values
    assert "c" in prof.sample_values


def test_profile_unique_count():
    values = ["x", "y", "x", "z", "y"]
    prof = profile_column("Letter", "letter", values)
    assert prof.unique_count == 3


def test_profile_normalized_name_stored():
    prof = profile_column("Province Name", "province_name", ["Lusaka"])
    assert prof.normalized_name == "province_name"
    assert prof.original_name == "Province Name"
