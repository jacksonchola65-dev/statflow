"""
tests/test_execute_rows.py
===========================
Focused tests for MappingExecutionService._execute_rows().

Covers:
- empty source row list
- one source row
- multiple source rows in order
- _execute_row called once per source row
- source rows not mutated
- fixed-value mappings across multiple rows
- transformations across multiple rows
- province transformation across multiple rows (real DB)
- failure on first / middle / final row
- processing stops after failing row
- original exception object is preserved (not wrapped)
"""

from __future__ import annotations

import copy
import sys
from decimal import Decimal
from unittest.mock import MagicMock, patch

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
# Empty input
# ---------------------------------------------------------------------------


async def test_empty_source_rows_returns_empty_list():
    cfg = _cfg(_col(TargetField.VALUE, "revenue"))
    result = await _svc()._execute_rows(cfg, [])
    assert result == []


# ---------------------------------------------------------------------------
# Single row
# ---------------------------------------------------------------------------


async def test_one_source_row_returns_one_result():
    cfg = _cfg(_col(TargetField.VALUE, "revenue"))
    rows = [{"revenue": "2500"}]
    result = await _svc()._execute_rows(cfg, rows)
    assert len(result) == 1
    assert result[0]["value"] == "2500"


async def test_one_row_with_fixed_value():
    cfg = _cfg(_fix(TargetField.INDICATOR_CODE, "ECOM_REVENUE"))
    result = await _svc()._execute_rows(cfg, [{}])
    assert result[0]["indicator_code"] == "ECOM_REVENUE"


# ---------------------------------------------------------------------------
# Multiple rows
# ---------------------------------------------------------------------------


async def test_multiple_rows_returns_same_count():
    cfg = _cfg(_col(TargetField.VALUE, "revenue"))
    rows = [{"revenue": "100"}, {"revenue": "200"}, {"revenue": "300"}]
    result = await _svc()._execute_rows(cfg, rows)
    assert len(result) == 3


async def test_original_row_order_preserved():
    cfg = _cfg(_col(TargetField.VALUE, "revenue"))
    rows = [{"revenue": "100"}, {"revenue": "200"}, {"revenue": "300"}]
    result = await _svc()._execute_rows(cfg, rows)
    assert result[0]["value"] == "100"
    assert result[1]["value"] == "200"
    assert result[2]["value"] == "300"


async def test_execute_row_called_once_per_source_row():
    """Verify _execute_row is called exactly N times for N rows."""
    cfg = _cfg(_col(TargetField.VALUE, "revenue"))
    rows = [{"revenue": str(i)} for i in range(5)]
    call_count = 0
    original_execute_row = MappingExecutionService._execute_row

    async def counting_execute_row(self, mapping_cfg, source_row):
        nonlocal call_count
        call_count += 1
        return await original_execute_row(self, mapping_cfg, source_row)

    svc = _svc()
    with patch.object(MappingExecutionService, "_execute_row", counting_execute_row):
        await svc._execute_rows(cfg, rows)

    assert call_count == 5


# ---------------------------------------------------------------------------
# Source rows not mutated
# ---------------------------------------------------------------------------


async def test_source_rows_not_mutated():
    cfg = _cfg(
        _col(
            TargetField.VALUE,
            "revenue",
            ops=[TransformationOperation.TRIM, TransformationOperation.PARSE_NUMBER],
        )
    )
    original_rows = [{"revenue": "  100  "}, {"revenue": "  200  "}]
    rows_copy = copy.deepcopy(original_rows)
    await _svc()._execute_rows(cfg, original_rows)
    assert original_rows == rows_copy


# ---------------------------------------------------------------------------
# Fixed-value mappings across multiple rows
# ---------------------------------------------------------------------------


async def test_fixed_value_same_across_all_rows():
    """A fixed-value mapping must produce the same value for every row."""
    cfg = _cfg(_fix(TargetField.DATASET_NAME, "Ecommerce Sales"))
    rows = [{}, {}, {}]
    result = await _svc()._execute_rows(cfg, rows)
    for r in result:
        assert r["dataset_name"] == "Ecommerce Sales"


# ---------------------------------------------------------------------------
# Transformations across multiple rows
# ---------------------------------------------------------------------------


async def test_parse_number_transformation_on_multiple_rows():
    cfg = _cfg(
        _col(
            TargetField.VALUE,
            "revenue",
            ops=[TransformationOperation.TRIM, TransformationOperation.PARSE_NUMBER],
        )
    )
    rows = [{"revenue": "  100  "}, {"revenue": "  200.5  "}, {"revenue": "  300  "}]
    result = await _svc()._execute_rows(cfg, rows)
    assert result[0]["value"] == Decimal("100")
    assert result[1]["value"] == Decimal("200.5")
    assert result[2]["value"] == Decimal("300")


async def test_extract_year_across_multiple_rows():
    cfg = _cfg(
        _col(
            TargetField.REFERENCE_YEAR,
            "order_date",
            ops=[TransformationOperation.TRIM, TransformationOperation.EXTRACT_YEAR],
        )
    )
    rows = [
        {"order_date": "2024-01-15"},
        {"order_date": "2023-06-30"},
        {"order_date": "2022-12-01"},
    ]
    result = await _svc()._execute_rows(cfg, rows)
    assert result[0]["reference_year"] == 2024
    assert result[1]["reference_year"] == 2023
    assert result[2]["reference_year"] == 2022


# ---------------------------------------------------------------------------
# Province transformation across multiple rows (real DB)
# ---------------------------------------------------------------------------


async def test_province_name_to_code_across_multiple_rows(db_session):
    cfg = _cfg(
        _col(
            TargetField.PROVINCE_CODE,
            "region",
            ops=[TransformationOperation.TRIM, TransformationOperation.PROVINCE_NAME_TO_CODE],
        )
    )
    rows = [
        {"region": "Lusaka"},
        {"region": "Central"},
        {"region": "Copperbelt"},
    ]
    svc = MappingExecutionService(session=db_session)
    result = await svc._execute_rows(cfg, rows)
    assert result[0]["province_code"] == "LK"
    assert result[1]["province_code"] == "CP"
    assert result[2]["province_code"] == "CB"


# ---------------------------------------------------------------------------
# Failure on first row
# ---------------------------------------------------------------------------


async def test_failure_on_first_row_stops_execution():
    cfg = _cfg(_col(TargetField.VALUE, "revenue", ops=[TransformationOperation.PARSE_NUMBER]))
    rows = [
        {"revenue": "bad_value"},  # row 0 — will fail
        {"revenue": "200"},  # row 1 — must never execute
        {"revenue": "300"},  # row 2 — must never execute
    ]
    with pytest.raises(TransformationExecutionError) as exc_info:
        await _svc()._execute_rows(cfg, rows)
    assert exc_info.value.operation == "parse_number"


async def test_only_first_row_processed_when_it_fails():
    """Verify row 1 and 2 are never attempted after row 0 fails."""
    cfg = _cfg(_col(TargetField.VALUE, "revenue", ops=[TransformationOperation.PARSE_NUMBER]))
    rows = [{"revenue": "bad"}, {"revenue": "200"}, {"revenue": "300"}]
    call_count = 0
    original = MappingExecutionService._execute_row

    async def counting(self, cfg_, row):
        nonlocal call_count
        call_count += 1
        return await original(self, cfg_, row)

    with patch.object(MappingExecutionService, "_execute_row", counting):
        with pytest.raises(TransformationExecutionError):
            await _svc()._execute_rows(cfg, rows)

    assert call_count == 1  # only the failing row was attempted


# ---------------------------------------------------------------------------
# Failure on a middle row
# ---------------------------------------------------------------------------


async def test_failure_on_middle_row_stops_at_that_row():
    cfg = _cfg(_col(TargetField.VALUE, "revenue", ops=[TransformationOperation.PARSE_NUMBER]))
    rows = [
        {"revenue": "100"},  # row 0 — succeeds
        {"revenue": "bad"},  # row 1 — fails
        {"revenue": "300"},  # row 2 — must never execute
    ]
    call_count = 0
    original = MappingExecutionService._execute_row

    async def counting(self, cfg_, row):
        nonlocal call_count
        call_count += 1
        return await original(self, cfg_, row)

    with patch.object(MappingExecutionService, "_execute_row", counting):
        with pytest.raises(TransformationExecutionError):
            await _svc()._execute_rows(cfg, rows)

    assert call_count == 2  # row 0 ok, row 1 fails, row 2 never reached


# ---------------------------------------------------------------------------
# Failure on the final row
# ---------------------------------------------------------------------------


async def test_failure_on_last_row_returns_error_not_partial_result():
    cfg = _cfg(_col(TargetField.VALUE, "revenue", ops=[TransformationOperation.PARSE_NUMBER]))
    rows = [
        {"revenue": "100"},  # succeeds
        {"revenue": "200"},  # succeeds
        {"revenue": "bad"},  # fails — last row
    ]
    with pytest.raises(TransformationExecutionError) as exc_info:
        await _svc()._execute_rows(cfg, rows)
    assert exc_info.value.operation == "parse_number"


# ---------------------------------------------------------------------------
# Original exception is preserved (not wrapped)
# ---------------------------------------------------------------------------


async def test_original_exception_object_is_not_wrapped():
    """The exact exception raised by _execute_row must propagate unchanged."""
    cfg = _cfg(_col(TargetField.VALUE, "missing_col"))
    rows = [{"other_col": "100"}]

    with pytest.raises(SourceColumnNotFoundError) as exc_info:
        await _svc()._execute_rows(cfg, rows)

    err = exc_info.value
    # Must be the original SourceColumnNotFoundError, not wrapped in something else
    assert isinstance(err, SourceColumnNotFoundError)
    assert err.column_name == "missing_col"
    assert err.target_field == "value"


async def test_transformation_exception_preserved_not_wrapped():
    cfg = _cfg(_col(TargetField.VALUE, "revenue", ops=[TransformationOperation.EXTRACT_YEAR]))
    rows = [{"revenue": "not-a-year"}]

    with pytest.raises(TransformationExecutionError) as exc_info:
        await _svc()._execute_rows(cfg, rows)

    err = exc_info.value
    assert isinstance(err, TransformationExecutionError)
    assert err.operation == "extract_year"
    # The raw_value must match what was in the cell
    assert err.raw_value == "not-a-year"
