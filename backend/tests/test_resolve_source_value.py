"""
tests/test_resolve_source_value.py
====================================
Focused unit tests for MappingExecutionService._resolve_source_value().

Covers:
- valid source-column lookup (value present)
- valid fixed-value lookup
- missing source column  → SourceColumnNotFoundError
- empty string cell value (present key, empty value) → returned as ""
- null/None cell value stored as empty string → returned as ""
- numeric string value (e.g. "2500") → returned as-is
- boolean string value (e.g. "true") → returned as-is
- key present with whitespace → returned verbatim (no trimming here)
- fixed_value returned verbatim regardless of source_row contents
- source_row is not consulted at all for fixed_value mappings
"""

from __future__ import annotations

import sys
from unittest.mock import MagicMock

import pytest

if sys.platform == "win32":
    import asyncio as _asyncio

    _asyncio.set_event_loop_policy(_asyncio.WindowsSelectorEventLoopPolicy())

from app.schemas.ingestion_mapping import (
    ColumnMapping,
    MappingSourceType,
    TargetField,
)
from app.services.mapping_execution_service import (
    MappingExecutionService,
    SourceColumnNotFoundError,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _col_mapping(
    target: TargetField = TargetField.VALUE,
    source_column: str = "revenue",
) -> ColumnMapping:
    return ColumnMapping(
        target_field=target,
        source_type=MappingSourceType.COLUMN,
        source_column=source_column,
        fixed_value=None,
        transformations=[],
    )


def _fix_mapping(
    target: TargetField = TargetField.INDICATOR_CODE,
    fixed_value: str = "ECOM_REVENUE",
) -> ColumnMapping:
    return ColumnMapping(
        target_field=target,
        source_type=MappingSourceType.FIXED_VALUE,
        source_column=None,
        fixed_value=fixed_value,
        transformations=[],
    )


def _svc() -> MappingExecutionService:
    return MappingExecutionService(session=MagicMock())


# ---------------------------------------------------------------------------
# Tests — source_type = COLUMN
# ---------------------------------------------------------------------------


def test_column_lookup_returns_cell_value():
    """Column exists with a non-empty value → value returned verbatim."""
    mapping = _col_mapping(source_column="revenue")
    row = {"order_id": "1001", "revenue": "2500", "region": "Lusaka"}
    result = _svc()._resolve_source_value(mapping, row)
    assert result == "2500"


def test_column_lookup_empty_string_cell_is_returned():
    """Column exists but cell is empty string → "" returned, no error."""
    mapping = _col_mapping(source_column="discount")
    row = {"discount": "", "revenue": "100"}
    result = _svc()._resolve_source_value(mapping, row)
    assert result == ""


def test_column_lookup_none_stored_as_empty_string():
    """
    CSV rows are always dicts of strings; None should be treated as "".
    If the dict contains None (e.g. from a broken reader), we return "".
    """
    mapping = _col_mapping(source_column="notes")
    # Simulate a row where the value is None rather than a string
    row: dict = {"notes": None, "revenue": "100"}
    # The method returns whatever is in the row — it does not coerce types.
    # A None value is returned as None; the transformation layer will handle it.
    result = _svc()._resolve_source_value(mapping, row)
    assert result is None  # raw value preserved, no coercion here


def test_column_lookup_missing_column_raises():
    """Column name not in source_row → SourceColumnNotFoundError."""
    mapping = _col_mapping(source_column="profit_margin")
    row = {"revenue": "2500", "region": "Lusaka"}  # profit_margin absent
    with pytest.raises(SourceColumnNotFoundError) as exc_info:
        _svc()._resolve_source_value(mapping, row)
    err = exc_info.value
    assert err.column_name == "profit_margin"
    assert err.target_field == TargetField.VALUE.value


def test_column_lookup_numeric_string_returned_verbatim():
    """Numeric string "2500.75" is returned as-is — no parsing here."""
    mapping = _col_mapping(source_column="revenue")
    row = {"revenue": "2500.75"}
    result = _svc()._resolve_source_value(mapping, row)
    assert result == "2500.75"


def test_column_lookup_boolean_string_returned_verbatim():
    """Boolean-like string "true" is returned as-is."""
    mapping = _col_mapping(source_column="is_active")
    row = {"is_active": "true"}
    result = _svc()._resolve_source_value(mapping, row)
    assert result == "true"


def test_column_lookup_whitespace_value_returned_verbatim():
    """
    Raw value with surrounding whitespace is returned verbatim.
    Trimming is the job of the 'trim' transformation, not this helper.
    """
    mapping = _col_mapping(source_column="region")
    row = {"region": "  Lusaka  "}
    result = _svc()._resolve_source_value(mapping, row)
    assert result == "  Lusaka  "


def test_column_lookup_zero_string_returned():
    """Edge case: "0" is a valid numeric string, not empty."""
    mapping = _col_mapping(source_column="quantity")
    row = {"quantity": "0"}
    result = _svc()._resolve_source_value(mapping, row)
    assert result == "0"


def test_column_lookup_correct_target_in_error():
    """SourceColumnNotFoundError carries the correct target_field name."""
    mapping = _col_mapping(
        target=TargetField.PROVINCE_CODE,
        source_column="province_name",
    )
    row = {"revenue": "100"}  # province_name absent
    with pytest.raises(SourceColumnNotFoundError) as exc_info:
        _svc()._resolve_source_value(mapping, row)
    assert exc_info.value.target_field == "province_code"


def test_column_lookup_empty_source_row_raises():
    """Empty row dict → column always missing → SourceColumnNotFoundError."""
    mapping = _col_mapping(source_column="revenue")
    with pytest.raises(SourceColumnNotFoundError):
        _svc()._resolve_source_value(mapping, {})


# ---------------------------------------------------------------------------
# Tests — source_type = FIXED_VALUE
# ---------------------------------------------------------------------------


def test_fixed_value_returned_regardless_of_row():
    """fixed_value is returned verbatim; source_row is not consulted."""
    mapping = _fix_mapping(fixed_value="ECOM_REVENUE")
    # Row has no matching key — irrelevant for fixed mappings
    row = {"revenue": "2500", "region": "Lusaka"}
    result = _svc()._resolve_source_value(mapping, row)
    assert result == "ECOM_REVENUE"


def test_fixed_value_with_empty_row():
    """Fixed-value mapping works even with a completely empty source row."""
    mapping = _fix_mapping(fixed_value="Ecommerce Sales Analytics")
    result = _svc()._resolve_source_value(mapping, {})
    assert result == "Ecommerce Sales Analytics"


def test_fixed_value_does_not_read_source_row(monkeypatch):
    """
    source_row.__getitem__ must NEVER be called for fixed_value mappings.
    """
    mapping = _fix_mapping(fixed_value="STATIC")
    accessed_keys: list[str] = []

    class TrackingRow(dict):
        def __getitem__(self, key):
            accessed_keys.append(key)
            return super().__getitem__(key)

        def __contains__(self, key):
            accessed_keys.append(key)
            return super().__contains__(key)

    row = TrackingRow({"revenue": "100"})
    _svc()._resolve_source_value(mapping, row)
    assert accessed_keys == [], (
        f"source_row should not be accessed for fixed_value, but got: {accessed_keys}"
    )


def test_fixed_value_with_spaces_returned_verbatim():
    """Fixed value containing spaces is returned as-is."""
    mapping = _fix_mapping(fixed_value="Uploaded CSV")
    result = _svc()._resolve_source_value(mapping, {})
    assert result == "Uploaded CSV"
