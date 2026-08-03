"""
tests/test_execute_row.py
==========================
Focused tests for MappingExecutionService._execute_row().

Covers:
- simple column mapping
- fixed-value mapping
- multiple mapped fields
- mixed fixed and source-column mappings
- transformation execution within a row
- missing source column error propagates
- transformation failure error propagates
- province lookup transformation (real DB)
- null cell value
- empty string cell value
- returned target-dict keys match configured target field names exactly
"""

from __future__ import annotations

import sys
from decimal import Decimal
from unittest.mock import MagicMock

import pytest

if sys.platform == "win32":
    import asyncio as _asyncio

    _asyncio.set_event_loop_policy(_asyncio.WindowsSelectorEventLoopPolicy())

from app.schemas.ingestion_mapping import (
    ColumnMapping,
    MappingConfiguration,
    MappingSourceType,
    TargetField,
    TransformationOperation,
    TransformationRule,
)
from app.services.mapping_execution_service import (
    MappingExecutionService,
    SourceColumnNotFoundError,
    TransformationExecutionError,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _col(
    target: TargetField, col: str, ops: list[TransformationOperation] | None = None
) -> ColumnMapping:
    return ColumnMapping(
        target_field=target,
        source_type=MappingSourceType.COLUMN,
        source_column=col,
        fixed_value=None,
        transformations=[TransformationRule(operation=op) for op in (ops or [])],
    )


def _fix(
    target: TargetField, value: str, ops: list[TransformationOperation] | None = None
) -> ColumnMapping:
    return ColumnMapping(
        target_field=target,
        source_type=MappingSourceType.FIXED_VALUE,
        source_column=None,
        fixed_value=value,
        transformations=[TransformationRule(operation=op) for op in (ops or [])],
    )


def _cfg(*mappings: ColumnMapping) -> MappingConfiguration:
    return MappingConfiguration.model_construct(mapping_version=1, mappings=list(mappings))


def _svc() -> MappingExecutionService:
    return MappingExecutionService(session=MagicMock())


# ---------------------------------------------------------------------------
# Simple column mapping
# ---------------------------------------------------------------------------


async def test_simple_column_mapping():
    cfg = _cfg(_col(TargetField.VALUE, "revenue"))
    row = {"revenue": "2500"}
    result = await _svc()._execute_row(cfg, row)
    assert result == {"value": "2500"}


async def test_column_mapping_uses_exact_cell_value():
    cfg = _cfg(_col(TargetField.PROVINCE_CODE, "region"))
    row = {"region": "Lusaka Province"}
    result = await _svc()._execute_row(cfg, row)
    assert result["province_code"] == "Lusaka Province"


# ---------------------------------------------------------------------------
# Fixed-value mapping
# ---------------------------------------------------------------------------


async def test_fixed_value_mapping():
    cfg = _cfg(_fix(TargetField.INDICATOR_CODE, "ECOM_REVENUE"))
    result = await _svc()._execute_row(cfg, {})
    assert result == {"indicator_code": "ECOM_REVENUE"}


async def test_fixed_value_independent_of_source_row():
    """Fixed-value mapping does not read source_row at all."""
    cfg = _cfg(_fix(TargetField.DATASET_NAME, "Ecommerce Sales"))
    result = await _svc()._execute_row(cfg, {"completely_different_col": "ignored"})
    assert result["dataset_name"] == "Ecommerce Sales"


# ---------------------------------------------------------------------------
# Multiple mapped fields
# ---------------------------------------------------------------------------


async def test_multiple_column_mappings():
    cfg = _cfg(
        _col(TargetField.PROVINCE_CODE, "region"),
        _col(TargetField.VALUE, "revenue"),
        _col(TargetField.REFERENCE_YEAR, "order_date"),
    )
    row = {"region": "Lusaka", "revenue": "2500", "order_date": "2024"}
    result = await _svc()._execute_row(cfg, row)
    assert result["province_code"] == "Lusaka"
    assert result["value"] == "2500"
    assert result["reference_year"] == "2024"


async def test_all_five_required_fields():
    cfg = _cfg(
        _col(TargetField.PROVINCE_CODE, "region"),
        _fix(TargetField.INDICATOR_CODE, "ECOM_REVENUE"),
        _col(TargetField.VALUE, "revenue"),
        _col(TargetField.REFERENCE_YEAR, "order_date"),
        _fix(TargetField.DATASET_NAME, "Ecommerce Sales"),
    )
    row = {"region": "Lusaka", "revenue": "2500", "order_date": "2024"}
    result = await _svc()._execute_row(cfg, row)
    assert set(result.keys()) == {
        "province_code",
        "indicator_code",
        "value",
        "reference_year",
        "dataset_name",
    }


# ---------------------------------------------------------------------------
# Mixed fixed and source-column mappings
# ---------------------------------------------------------------------------


async def test_mixed_fixed_and_column_mappings():
    cfg = _cfg(
        _col(TargetField.PROVINCE_CODE, "region"),
        _fix(TargetField.INDICATOR_CODE, "ECOM_REVENUE"),
        _col(TargetField.VALUE, "revenue"),
        _col(TargetField.REFERENCE_YEAR, "year"),
        _fix(TargetField.DATASET_NAME, "Ecommerce Sales"),
        _fix(TargetField.SOURCE_NAME, "Uploaded CSV"),
    )
    row = {"region": "Lusaka", "revenue": "2500", "year": "2024"}
    result = await _svc()._execute_row(cfg, row)
    assert result["province_code"] == "Lusaka"
    assert result["indicator_code"] == "ECOM_REVENUE"
    assert result["value"] == "2500"
    assert result["reference_year"] == "2024"
    assert result["dataset_name"] == "Ecommerce Sales"
    assert result["source_name"] == "Uploaded CSV"


# ---------------------------------------------------------------------------
# Transformation execution
# ---------------------------------------------------------------------------


async def test_transformation_applied_to_column_value():
    cfg = _cfg(
        _col(
            TargetField.VALUE,
            "revenue",
            ops=[TransformationOperation.TRIM, TransformationOperation.PARSE_NUMBER],
        )
    )
    row = {"revenue": "  2500.75  "}
    result = await _svc()._execute_row(cfg, row)
    assert result["value"] == Decimal("2500.75")


async def test_transformation_applied_to_fixed_value():
    cfg = _cfg(
        _fix(TargetField.INDICATOR_CODE, "ecom_revenue", ops=[TransformationOperation.UPPERCASE])
    )
    result = await _svc()._execute_row(cfg, {})
    assert result["indicator_code"] == "ECOM_REVENUE"


async def test_extract_year_transformation():
    cfg = _cfg(
        _col(
            TargetField.REFERENCE_YEAR,
            "order_date",
            ops=[TransformationOperation.TRIM, TransformationOperation.EXTRACT_YEAR],
        )
    )
    row = {"order_date": "  2024-06-15  "}
    result = await _svc()._execute_row(cfg, row)
    assert result["reference_year"] == 2024


# ---------------------------------------------------------------------------
# Missing source column
# ---------------------------------------------------------------------------


async def test_missing_source_column_raises():
    cfg = _cfg(_col(TargetField.VALUE, "nonexistent_col"))
    with pytest.raises(SourceColumnNotFoundError) as exc_info:
        await _svc()._execute_row(cfg, {"other_col": "100"})
    assert exc_info.value.column_name == "nonexistent_col"
    assert exc_info.value.target_field == "value"


async def test_missing_column_stops_row_execution():
    """When one mapping fails due to missing column, subsequent mappings are not executed."""
    cfg = _cfg(
        _col(TargetField.PROVINCE_CODE, "missing_col"),  # will fail
        _col(TargetField.VALUE, "revenue"),  # should never execute
    )
    with pytest.raises(SourceColumnNotFoundError):
        await _svc()._execute_row(cfg, {"revenue": "100"})


# ---------------------------------------------------------------------------
# Transformation failure
# ---------------------------------------------------------------------------


async def test_transformation_failure_propagates():
    cfg = _cfg(_col(TargetField.VALUE, "revenue", ops=[TransformationOperation.PARSE_NUMBER]))
    row = {"revenue": "not_a_number"}
    with pytest.raises(TransformationExecutionError) as exc_info:
        await _svc()._execute_row(cfg, row)
    assert exc_info.value.operation == "parse_number"


async def test_transformation_failure_stops_row():
    """A transformation failure on one field stops processing subsequent fields."""
    cfg = _cfg(
        _col(TargetField.VALUE, "revenue", ops=[TransformationOperation.PARSE_NUMBER]),  # will fail
        _col(TargetField.REFERENCE_YEAR, "year"),  # should not execute
    )
    row = {"revenue": "bad", "year": "2024"}
    with pytest.raises(TransformationExecutionError):
        await _svc()._execute_row(cfg, row)


# ---------------------------------------------------------------------------
# Province lookup transformation (real DB)
# ---------------------------------------------------------------------------


async def test_province_name_to_code_in_execute_row(db_session):
    cfg = _cfg(
        _col(
            TargetField.PROVINCE_CODE,
            "region",
            ops=[TransformationOperation.TRIM, TransformationOperation.PROVINCE_NAME_TO_CODE],
        )
    )
    row = {"region": "  Lusaka  "}
    svc = MappingExecutionService(session=db_session)
    result = await svc._execute_row(cfg, row)
    assert result["province_code"] == "LK"


async def test_unknown_province_in_execute_row(db_session):
    cfg = _cfg(
        _col(
            TargetField.PROVINCE_CODE, "region", ops=[TransformationOperation.PROVINCE_NAME_TO_CODE]
        )
    )
    row = {"region": "Atlantis"}
    svc = MappingExecutionService(session=db_session)
    with pytest.raises(TransformationExecutionError) as exc_info:
        await svc._execute_row(cfg, row)
    assert exc_info.value.operation == "province_name_to_code"


# ---------------------------------------------------------------------------
# Null and empty string cell values
# ---------------------------------------------------------------------------


async def test_null_cell_value_stored_as_none():
    """A cell containing None passes through with no transformations."""
    cfg = _cfg(_col(TargetField.SOURCE_NAME, "notes"))
    row: dict = {"notes": None}
    result = await _svc()._execute_row(cfg, row)
    assert result["source_name"] is None


async def test_empty_string_cell_stored():
    """An empty string cell is stored as-is (no transformations)."""
    cfg = _cfg(_col(TargetField.SOURCE_NAME, "notes"))
    row = {"notes": ""}
    result = await _svc()._execute_row(cfg, row)
    assert result["source_name"] == ""


async def test_trim_on_empty_string_returns_empty():
    cfg = _cfg(_col(TargetField.SOURCE_NAME, "notes", ops=[TransformationOperation.TRIM]))
    row = {"notes": ""}
    result = await _svc()._execute_row(cfg, row)
    assert result["source_name"] == ""


# ---------------------------------------------------------------------------
# Returned target keys exactly match configured target field names
# ---------------------------------------------------------------------------


async def test_target_keys_match_field_names():
    cfg = _cfg(
        _col(TargetField.PROVINCE_CODE, "region"),
        _fix(TargetField.INDICATOR_CODE, "IND"),
        _col(TargetField.VALUE, "revenue"),
        _col(TargetField.REFERENCE_YEAR, "year"),
        _fix(TargetField.DATASET_NAME, "DS"),
    )
    row = {"region": "Lusaka", "revenue": "100", "year": "2024"}
    result = await _svc()._execute_row(cfg, row)
    expected_keys = {"province_code", "indicator_code", "value", "reference_year", "dataset_name"}
    assert set(result.keys()) == expected_keys


async def test_source_name_key_when_included():
    cfg = _cfg(_fix(TargetField.SOURCE_NAME, "Uploaded CSV"))
    result = await _svc()._execute_row(cfg, {})
    assert "source_name" in result
    assert result["source_name"] == "Uploaded CSV"


async def test_no_extra_keys_in_result():
    """The result dict contains ONLY the target fields from the mapping config."""
    cfg = _cfg(
        _col(TargetField.VALUE, "revenue"),
    )
    row = {"revenue": "100", "order_id": "999", "extra_col": "ignored"}
    result = await _svc()._execute_row(cfg, row)
    assert set(result.keys()) == {"value"}


async def test_result_does_not_contain_source_row_columns():
    """Source row column names must not appear as keys in the result."""
    cfg = _cfg(_col(TargetField.VALUE, "revenue"))
    row = {"revenue": "100"}
    result = await _svc()._execute_row(cfg, row)
    assert "revenue" not in result
