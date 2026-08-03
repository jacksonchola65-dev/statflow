"""
tests/test_apply_transformation.py
=====================================
Focused unit tests for MappingExecutionService._apply_transformation().

Phase coverage: trim only.

Test matrix
-----------
trim:
  - normal string with internal value     → unchanged
  - leading whitespace                    → stripped
  - trailing whitespace                   → stripped
  - leading + trailing whitespace         → both stripped
  - tabs                                  → stripped
  - newlines                              → stripped
  - empty string                          → ""
  - whitespace-only string               → ""
  - None                                  → None (non-string passthrough)
  - integer                               → integer unchanged
  - float                                 → float unchanged
  - Decimal                               → Decimal unchanged
  - boolean True                          → True unchanged
  - boolean False                         → False unchanged

unsupported operations:
  - uppercase    → UnsupportedTransformationError
  - lowercase    → UnsupportedTransformationError
  - parse_number → UnsupportedTransformationError
  - extract_year → UnsupportedTransformationError
  - province_name_to_code → UnsupportedTransformationError
"""

from __future__ import annotations

import sys
from decimal import Decimal

import pytest

if sys.platform == "win32":
    import asyncio as _asyncio

    _asyncio.set_event_loop_policy(_asyncio.WindowsSelectorEventLoopPolicy())

from app.schemas.ingestion_mapping import TransformationOperation
from app.services.mapping_execution_service import (
    MappingExecutionService,
    UnsupportedTransformationError,
)

# Convenience alias — _apply_transformation is a staticmethod
_apply = MappingExecutionService._apply_transformation
TRIM = TransformationOperation.TRIM


# ---------------------------------------------------------------------------
# trim — string inputs
# ---------------------------------------------------------------------------


def test_trim_normal_string_unchanged():
    """A string with no surrounding whitespace is returned unchanged."""
    assert _apply(TRIM, "Lusaka") == "Lusaka"


def test_trim_leading_whitespace():
    assert _apply(TRIM, "  Lusaka") == "Lusaka"


def test_trim_trailing_whitespace():
    assert _apply(TRIM, "Lusaka  ") == "Lusaka"


def test_trim_both_sides():
    assert _apply(TRIM, "  Lusaka  ") == "Lusaka"


def test_trim_tab_characters():
    assert _apply(TRIM, "\tLusaka\t") == "Lusaka"


def test_trim_newlines():
    assert _apply(TRIM, "\nLusaka\n") == "Lusaka"


def test_trim_mixed_whitespace():
    """Tab + space + newline mix on both sides."""
    assert _apply(TRIM, " \t Lusaka \n ") == "Lusaka"


def test_trim_empty_string_returns_empty():
    assert _apply(TRIM, "") == ""


def test_trim_whitespace_only_string_returns_empty():
    assert _apply(TRIM, "   ") == ""


def test_trim_internal_spaces_preserved():
    """Whitespace inside the string is NOT removed by trim."""
    assert _apply(TRIM, "  North Western  ") == "North Western"


# ---------------------------------------------------------------------------
# trim — non-string inputs (passthrough)
# ---------------------------------------------------------------------------


def test_trim_none_returns_none():
    """None is not a string → returned unchanged."""
    assert _apply(TRIM, None) is None


def test_trim_integer_returned_unchanged():
    assert _apply(TRIM, 2023) == 2023
    assert isinstance(_apply(TRIM, 2023), int)


def test_trim_float_returned_unchanged():
    result = _apply(TRIM, 2500.75)
    assert result == 2500.75
    assert isinstance(result, float)


def test_trim_decimal_returned_unchanged():
    d = Decimal("1234.56")
    result = _apply(TRIM, d)
    assert result == d
    assert isinstance(result, Decimal)


def test_trim_boolean_true_returned_unchanged():
    result = _apply(TRIM, True)
    assert result is True


def test_trim_boolean_false_returned_unchanged():
    result = _apply(TRIM, False)
    assert result is False


# ---------------------------------------------------------------------------
# Unsupported operations
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "op",
    [
        TransformationOperation.PROVINCE_NAME_TO_CODE,
    ],
)
def test_unsupported_operation_raises(op):
    """Every non-trim operation raises UnsupportedTransformationError."""
    with pytest.raises(UnsupportedTransformationError) as exc_info:
        _apply(op, "some value")
    assert exc_info.value.operation == op.value


def test_unsupported_error_message_contains_operation_name():
    """The error message must name the unsupported operation."""
    with pytest.raises(UnsupportedTransformationError) as exc_info:
        _apply(TransformationOperation.PROVINCE_NAME_TO_CODE, "Lusaka")
    assert "province_name_to_code" in str(exc_info.value).lower()


# ---------------------------------------------------------------------------
# uppercase — added in current phase
# ---------------------------------------------------------------------------

UPPER = TransformationOperation.UPPERCASE


def test_uppercase_lowercase_string():
    assert _apply(UPPER, "lusaka") == "LUSAKA"


def test_uppercase_mixed_case_string():
    assert _apply(UPPER, "North-Western") == "NORTH-WESTERN"


def test_uppercase_already_uppercase():
    assert _apply(UPPER, "ECOM_REVENUE") == "ECOM_REVENUE"


def test_uppercase_preserves_surrounding_whitespace():
    """uppercase does NOT trim — whitespace is preserved."""
    assert _apply(UPPER, "  lusaka  ") == "  LUSAKA  "


def test_uppercase_empty_string():
    assert _apply(UPPER, "") == ""


def test_uppercase_none_returns_none():
    assert _apply(UPPER, None) is None


def test_uppercase_integer_unchanged():
    assert _apply(UPPER, 2023) == 2023


def test_uppercase_float_unchanged():
    assert _apply(UPPER, 3.14) == 3.14


def test_uppercase_boolean_true_unchanged():
    assert _apply(UPPER, True) is True


def test_uppercase_boolean_false_unchanged():
    assert _apply(UPPER, False) is False


# ---------------------------------------------------------------------------
# Regression — trim still works after uppercase was added
# ---------------------------------------------------------------------------


def test_trim_regression_still_works():
    assert _apply(TRIM, "  Lusaka  ") == "Lusaka"


def test_trim_regression_none_passthrough():
    assert _apply(TRIM, None) is None


# ---------------------------------------------------------------------------
# Unsupported-operation regression — uppercase now supported, lowercase still not
# ---------------------------------------------------------------------------


def test_lowercase_still_unsupported():
    """lowercase is now supported — this test verifies it no longer raises."""
    result = _apply(TransformationOperation.LOWERCASE, "HELLO")
    assert result == "hello"


def test_parse_number_still_unsupported():
    """parse_number is now supported — verify it returns a Decimal."""
    from decimal import Decimal

    assert _apply(TransformationOperation.PARSE_NUMBER, "100") == Decimal("100")


def test_extract_year_still_unsupported():
    """extract_year is now supported — verify it returns an int."""
    assert _apply(TransformationOperation.EXTRACT_YEAR, "2025-04-10") == 2025


def test_province_name_to_code_still_unsupported():
    with pytest.raises(UnsupportedTransformationError):
        _apply(TransformationOperation.PROVINCE_NAME_TO_CODE, "Lusaka")


# ---------------------------------------------------------------------------
# lowercase — added in current phase
# ---------------------------------------------------------------------------

LOWER = TransformationOperation.LOWERCASE


def test_lowercase_uppercase_string():
    assert _apply(LOWER, "LUSAKA") == "lusaka"


def test_lowercase_mixed_case_string():
    assert _apply(LOWER, "North-Western") == "north-western"


def test_lowercase_already_lowercase():
    assert _apply(LOWER, "ecom_revenue") == "ecom_revenue"


def test_lowercase_preserves_surrounding_whitespace():
    """lowercase does NOT trim — whitespace is preserved."""
    assert _apply(LOWER, "  LUSAKA  ") == "  lusaka  "


def test_lowercase_empty_string():
    assert _apply(LOWER, "") == ""


def test_lowercase_none_returns_none():
    assert _apply(LOWER, None) is None


def test_lowercase_integer_unchanged():
    assert _apply(LOWER, 2023) == 2023


def test_lowercase_float_unchanged():
    assert _apply(LOWER, 3.14) == 3.14


def test_lowercase_boolean_true_unchanged():
    assert _apply(LOWER, True) is True


def test_lowercase_boolean_false_unchanged():
    assert _apply(LOWER, False) is False


# ---------------------------------------------------------------------------
# Regression — trim and uppercase still work after lowercase was added
# ---------------------------------------------------------------------------


def test_trim_regression_after_lowercase():
    assert _apply(TRIM, "  Lusaka  ") == "Lusaka"


def test_uppercase_regression_after_lowercase():
    assert _apply(TransformationOperation.UPPERCASE, "lusaka") == "LUSAKA"


# ---------------------------------------------------------------------------
# Unsupported-operation regression — only three ops remain unsupported
# ---------------------------------------------------------------------------


def test_parse_number_still_unsupported_after_lowercase():
    """parse_number is now supported — verify it returns a Decimal."""
    from decimal import Decimal

    assert _apply(TransformationOperation.PARSE_NUMBER, "42.5") == Decimal("42.5")


def test_extract_year_still_unsupported_after_lowercase():
    """extract_year is now supported — verify it returns an int."""
    assert _apply(TransformationOperation.EXTRACT_YEAR, "2024-06-15") == 2024


def test_province_name_to_code_still_unsupported_after_lowercase():
    with pytest.raises(UnsupportedTransformationError):
        _apply(TransformationOperation.PROVINCE_NAME_TO_CODE, "Lusaka")


# ---------------------------------------------------------------------------
# parse_number — added in current phase
# ---------------------------------------------------------------------------

from decimal import Decimal as _D

PARSE = TransformationOperation.PARSE_NUMBER


def test_parse_number_integer_input_unchanged():
    """int passes through unchanged."""
    assert _apply(PARSE, 42) == 42
    assert isinstance(_apply(PARSE, 42), int)


def test_parse_number_float_input_unchanged():
    """float passes through unchanged."""
    assert _apply(PARSE, 3.14) == 3.14
    assert isinstance(_apply(PARSE, 3.14), float)


def test_parse_number_decimal_input_unchanged():
    """Decimal passes through unchanged."""
    d = _D("99.99")
    assert _apply(PARSE, d) == d
    assert isinstance(_apply(PARSE, d), _D)


def test_parse_number_boolean_true_unchanged():
    """bool is a subclass of int — must pass through without being parsed."""
    result = _apply(PARSE, True)
    assert result is True
    assert isinstance(result, bool)


def test_parse_number_boolean_false_unchanged():
    result = _apply(PARSE, False)
    assert result is False
    assert isinstance(result, bool)


def test_parse_number_none_returns_none():
    assert _apply(PARSE, None) is None


def test_parse_number_positive_integer_string():
    result = _apply(PARSE, "42")
    assert result == _D("42")
    assert isinstance(result, _D)


def test_parse_number_negative_integer_string():
    result = _apply(PARSE, "-10")
    assert result == _D("-10")


def test_parse_number_decimal_string():
    result = _apply(PARSE, "42.5")
    assert result == _D("42.5")


def test_parse_number_negative_decimal_string():
    result = _apply(PARSE, "-3.14")
    assert result == _D("-3.14")


def test_parse_number_surrounding_whitespace_stripped():
    """Leading/trailing whitespace is ignored during parsing."""
    result = _apply(PARSE, "  100  ")
    assert result == _D("100")


def test_parse_number_comma_formatted_integer():
    """Commas as thousands separators must be removed before parsing."""
    result = _apply(PARSE, "1,250")
    assert result == _D("1250")


def test_parse_number_comma_formatted_decimal():
    result = _apply(PARSE, "1,250.50")
    assert result == _D("1250.50")


def test_parse_number_comma_formatted_large():
    result = _apply(PARSE, "1,000,000.99")
    assert result == _D("1000000.99")


def test_parse_number_empty_string_raises():
    from app.services.mapping_execution_service import TransformationExecutionError

    with pytest.raises(TransformationExecutionError) as exc_info:
        _apply(PARSE, "")
    assert exc_info.value.operation == "parse_number"


def test_parse_number_whitespace_only_string_raises():
    from app.services.mapping_execution_service import TransformationExecutionError

    with pytest.raises(TransformationExecutionError):
        _apply(PARSE, "   ")


def test_parse_number_alphabetic_string_raises():
    from app.services.mapping_execution_service import TransformationExecutionError

    with pytest.raises(TransformationExecutionError) as exc_info:
        _apply(PARSE, "abc")
    assert "abc" in str(exc_info.value)


def test_parse_number_malformed_string_raises():
    from app.services.mapping_execution_service import TransformationExecutionError

    with pytest.raises(TransformationExecutionError):
        _apply(PARSE, "12.34.56")


# ---------------------------------------------------------------------------
# Regression — trim, uppercase, lowercase still work after parse_number added
# ---------------------------------------------------------------------------


def test_trim_regression_after_parse_number():
    assert _apply(TRIM, "  Lusaka  ") == "Lusaka"


def test_uppercase_regression_after_parse_number():
    assert _apply(TransformationOperation.UPPERCASE, "lusaka") == "LUSAKA"


def test_lowercase_regression_after_parse_number():
    assert _apply(TransformationOperation.LOWERCASE, "LUSAKA") == "lusaka"


# ---------------------------------------------------------------------------
# Unsupported-operation regression — two ops still unsupported
# ---------------------------------------------------------------------------


def test_extract_year_still_unsupported_after_parse_number():
    """extract_year is now supported."""
    assert _apply(TransformationOperation.EXTRACT_YEAR, "2025") == 2025


def test_province_name_to_code_still_unsupported_after_parse_number():
    with pytest.raises(UnsupportedTransformationError):
        _apply(TransformationOperation.PROVINCE_NAME_TO_CODE, "Lusaka")


# ---------------------------------------------------------------------------
# extract_year — added in current phase
# ---------------------------------------------------------------------------

from app.services.mapping_execution_service import TransformationExecutionError as _TxError

EY = TransformationOperation.EXTRACT_YEAR


def test_extract_year_integer_year_unchanged():
    assert _apply(EY, 2024) == 2024
    assert isinstance(_apply(EY, 2024), int)


def test_extract_year_lower_boundary_1900():
    assert _apply(EY, 1900) == 1900


def test_extract_year_upper_boundary_2100():
    assert _apply(EY, 2100) == 2100


def test_extract_year_below_range_raises():
    with pytest.raises(_TxError) as exc_info:
        _apply(EY, 1899)
    assert "1899" in str(exc_info.value)


def test_extract_year_above_range_raises():
    with pytest.raises(_TxError):
        _apply(EY, 2101)


def test_extract_year_four_digit_string():
    assert _apply(EY, "2024") == 2024
    assert isinstance(_apply(EY, "2024"), int)


def test_extract_year_yyyy_mm_dd():
    assert _apply(EY, "2024-06-15") == 2024


def test_extract_year_yyyy_slash_mm_slash_dd():
    assert _apply(EY, "2024/06/15") == 2024


def test_extract_year_dd_mm_yyyy_dash():
    assert _apply(EY, "15-06-2024") == 2024


def test_extract_year_dd_mm_yyyy_slash():
    assert _apply(EY, "15/06/2024") == 2024


def test_extract_year_mm_dd_yyyy_dash():
    assert _apply(EY, "06-15-2024") == 2024


def test_extract_year_mm_dd_yyyy_slash():
    assert _apply(EY, "06/15/2024") == 2024


def test_extract_year_iso_datetime_with_z():
    assert _apply(EY, "2024-06-15T10:30:00Z") == 2024


def test_extract_year_iso_datetime_without_z():
    assert _apply(EY, "2024-06-15T10:30:00") == 2024


def test_extract_year_surrounding_whitespace():
    assert _apply(EY, "  2024  ") == 2024
    assert _apply(EY, "  2024-06-15  ") == 2024


def test_extract_year_none_returns_none():
    assert _apply(EY, None) is None


def test_extract_year_empty_string_raises():
    with pytest.raises(_TxError) as exc_info:
        _apply(EY, "")
    assert exc_info.value.operation == "extract_year"


def test_extract_year_whitespace_only_raises():
    with pytest.raises(_TxError):
        _apply(EY, "   ")


def test_extract_year_invalid_date_text_raises():
    with pytest.raises(_TxError):
        _apply(EY, "not-a-date")


def test_extract_year_string_without_year_raises():
    with pytest.raises(_TxError):
        _apply(EY, "hello world")


def test_extract_year_boolean_raises():
    with pytest.raises(_TxError) as exc_info:
        _apply(EY, True)
    assert exc_info.value.operation == "extract_year"


def test_extract_year_float_raises():
    with pytest.raises(_TxError):
        _apply(EY, 2024.5)


def test_extract_year_decimal_raises():
    from decimal import Decimal

    with pytest.raises(_TxError):
        _apply(EY, Decimal("2024"))


def test_extract_year_string_year_below_range_raises():
    with pytest.raises(_TxError):
        _apply(EY, "1800")


def test_extract_year_string_year_above_range_raises():
    with pytest.raises(_TxError):
        _apply(EY, "2200")


# ---------------------------------------------------------------------------
# Full regression suite after extract_year added
# ---------------------------------------------------------------------------


def test_trim_regression_after_extract_year():
    assert _apply(TRIM, "  Lusaka  ") == "Lusaka"


def test_uppercase_regression_after_extract_year():
    assert _apply(TransformationOperation.UPPERCASE, "lusaka") == "LUSAKA"


def test_lowercase_regression_after_extract_year():
    assert _apply(TransformationOperation.LOWERCASE, "LUSAKA") == "lusaka"


def test_parse_number_regression_after_extract_year():
    from decimal import Decimal

    assert _apply(TransformationOperation.PARSE_NUMBER, "42.5") == Decimal("42.5")


def test_province_name_to_code_still_unsupported_after_extract_year():
    with pytest.raises(UnsupportedTransformationError):
        _apply(TransformationOperation.PROVINCE_NAME_TO_CODE, "Lusaka")
