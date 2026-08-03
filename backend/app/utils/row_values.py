"""
utils/row_values.py
===================
Validation and serialization helpers for DatasetRow.values.

A DatasetRow.values dict must satisfy:
  - It is a dict (not a list, scalar, or None).
  - Every key is a non-empty string (the normalized column name).
  - Every value is JSON-compatible: None, bool, int, finite float/Decimal,
    or str. ISO-formatted date/datetime strings are already str and pass.

Rejected values:
  - float('nan'), float('inf'), float('-inf')
  - Decimal('NaN'), Decimal('Infinity')
  - Objects with no safe JSON representation (bytes, sets, custom classes …)

Usage:
    from app.utils.row_values import validate_row_values, serialize_row_values

    # Raises RowValuesError with a descriptive message on failure:
    clean = serialize_row_values({"col_a": 1, "col_b": "hello", "col_c": None})
    validate_row_values(clean)   # no-op if already clean
"""

from __future__ import annotations

import math
from decimal import Decimal
from typing import Any


class RowValuesError(ValueError):
    """Raised when a row values dict violates the DatasetRow contract."""


def _format_decimal_to_string(d: Decimal) -> str:
    """Convert a finite Decimal to fixed-point string representation.

    Preserves:
    - Full precision of all significant digits
    - Trailing zeros (as represented in the Decimal)
    - Sign (positive/negative)
    - Exact scale (no scientific notation)

    Examples:
        Decimal("0.0000000001") -> "0.0000000001"
        Decimal("100.00") -> "100.00"
        Decimal("27.345678901234567890") -> "27.345678901234567890"
        Decimal("-0.00010") -> "-0.00010"

    Assumes the Decimal is already validated as finite.
    """
    sign, digits, exponent = d.as_tuple()

    # Handle empty digits (shouldn't happen for finite values, but be defensive)
    if not digits:
        return "-0" if sign else "0"

    # Construct the coefficient (the significant digits as a string)
    coefficient = "".join(map(str, digits))

    if exponent >= 0:
        # Positive exponent: trailing zeros (e.g., 100 with exp=2 is 10000)
        result = coefficient + "0" * exponent
    else:
        # Negative exponent: decimal point needed
        abs_exponent = -exponent

        if abs_exponent >= len(coefficient):
            # All digits are fractional (e.g., "1" with exp=-10 is 0.0000000001)
            result = "0." + "0" * (abs_exponent - len(coefficient)) + coefficient
        else:
            # Decimal point in the middle (e.g., "12345" with exp=-2 is 123.45)
            split_point = len(coefficient) - abs_exponent
            result = coefficient[:split_point] + "." + coefficient[split_point:]

    # Prepend sign if negative
    if sign:
        result = "-" + result

    return result


def _serialize_scalar(key: str, value: Any) -> Any:
    """Convert a single value to a JSON-compatible scalar.

    Raises RowValuesError for unsupported or non-finite numeric values.
    """
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            raise RowValuesError(
                f"Column '{key}': float value must be finite; NaN and infinity are not permitted."
            )
        return value
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise RowValuesError(
                f"Column '{key}': Decimal value must be finite; NaN and infinity are not permitted."
            )
        # Convert to fixed-point string with full precision and trailing zeros.
        return _format_decimal_to_string(value)
    if isinstance(value, str):
        return value
    raise RowValuesError(
        f"Column '{key}': value of type '{type(value).__name__}' is not "
        f"JSON-compatible. Supported types: None, bool, int, float, Decimal, str."
    )


def serialize_row_values(raw: dict[str, Any]) -> dict[str, Any]:
    """Convert a raw dict of column values to a JSON-compatible dict.

    - Input must be a dict.
    - Each key must be a non-empty string.
    - Each value is passed through _serialize_scalar.

    Raises RowValuesError on any violation.
    Returns a new dict with converted values.
    """
    if not isinstance(raw, dict):
        raise RowValuesError(f"row values must be a dict (JSON object); got {type(raw).__name__}.")
    result: dict[str, Any] = {}
    for key, value in raw.items():
        if not isinstance(key, str) or not key.strip():
            raise RowValuesError(f"Row values dict key must be a non-empty string; got {key!r}.")
        result[key] = _serialize_scalar(key, value)
    return result


def validate_row_values(values: Any) -> None:
    """Assert that *values* is a dict of JSON-compatible scalars.

    Suitable for use after deserializing from the database to catch
    any corrupt stored data. Raises RowValuesError on failure.
    """
    if not isinstance(values, dict):
        raise RowValuesError(
            f"row values must be a JSON object (dict); got {type(values).__name__}."
        )
    for key, value in values.items():
        _serialize_scalar(key, value)
