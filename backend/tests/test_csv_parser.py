"""
test_csv_parser.py
==================
Unit tests for parse_and_validate — the pure CSV parser/validator.

All tests call parse_and_validate directly with in-memory fixture dicts.
No database connections are made.

References: REQ-2.2, REQ-2.6, REQ-2.7, REQ-3, REQ-4, REQ-12.1–REQ-12.8
"""
from __future__ import annotations

import textwrap
from uuid import uuid4

import pytest

from app.utils.csv_parser import (
    MalformedCsvError,
    MissingColumnsError,
    ParseResult,
    parse_and_validate,
)

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------

PROVINCE_MAP = {"CP": uuid4(), "LP": uuid4()}
INDICATOR_MAP = {"GDPC": uuid4(), "POP": uuid4()}
EXISTING_DATASET_NAMES: set[str] = {"ExistingDataset"}


def _build_csv(*rows: str) -> bytes:
    """
    Combine a header + data rows into UTF-8 CSV bytes.

    Each row is already a full CSV line string.  The helper exists solely to
    avoid repeating the encode step in every test.
    """
    header = "province_code,indicator_code,value,reference_year,dataset_name,source_name,source_url"
    lines = "\n".join([header, *rows])
    return lines.encode("utf-8")


# ---------------------------------------------------------------------------
# Test 1 — Valid 3-row CSV
# REQ-12.1
# ---------------------------------------------------------------------------

def test_valid_three_row_csv():
    """Valid CSV with 3 rows produces valid_rows=3, no errors, no duplicates."""
    csv_bytes = _build_csv(
        "CP,GDPC,1000.50,2020,MyDataset,National Bureau,",
        "LP,GDPC,2000.00,2020,MyDataset,National Bureau,",
        "CP,POP,500000,2021,MyDataset,National Bureau,",
    )
    result = parse_and_validate(
        csv_bytes, PROVINCE_MAP, INDICATOR_MAP, EXISTING_DATASET_NAMES
    )
    assert len(result.valid_rows) == 3
    assert result.errors == []
    assert result.duplicate_row_numbers == []


# ---------------------------------------------------------------------------
# Test 2 — Missing required column: dataset_name
# REQ-2.2, REQ-12.3
# ---------------------------------------------------------------------------

def test_missing_required_column_raises():
    """CSV without dataset_name column must raise MissingColumnsError."""
    csv_bytes = textwrap.dedent("""\
        province_code,indicator_code,value,reference_year,source_name
        CP,GDPC,1000,2020,SomeSource
    """).encode("utf-8")

    with pytest.raises(MissingColumnsError) as exc_info:
        parse_and_validate(
            csv_bytes, PROVINCE_MAP, INDICATOR_MAP, EXISTING_DATASET_NAMES
        )

    assert "dataset_name" in exc_info.value.missing


# ---------------------------------------------------------------------------
# Test 3 — Blank dataset_name cell
# REQ-2.6
# ---------------------------------------------------------------------------

def test_blank_dataset_name_produces_row_error():
    """A row with a blank dataset_name cell must produce a row-level error."""
    csv_bytes = _build_csv("CP,GDPC,1000,2020,,SomeSource,")

    result = parse_and_validate(
        csv_bytes, PROVINCE_MAP, INDICATOR_MAP, EXISTING_DATASET_NAMES
    )

    assert len(result.valid_rows) == 0
    assert any(e.column == "dataset_name" for e in result.errors)


# ---------------------------------------------------------------------------
# Test 4 — New dataset_name + blank source_name → error
# REQ-2.7
# ---------------------------------------------------------------------------

def test_new_dataset_blank_source_name_produces_row_error():
    """
    When dataset_name is not in existing_dataset_names, source_name must
    be non-empty.  A blank source_name is a row-level validation error.
    """
    csv_bytes = _build_csv("CP,GDPC,1000,2020,BrandNewDataset,,")

    result = parse_and_validate(
        csv_bytes, PROVINCE_MAP, INDICATOR_MAP, EXISTING_DATASET_NAMES
    )

    assert len(result.valid_rows) == 0
    assert any(e.column == "source_name" for e in result.errors)


# ---------------------------------------------------------------------------
# Test 5 — Existing dataset_name + blank source_name → valid
# REQ-2.7
# ---------------------------------------------------------------------------

def test_existing_dataset_blank_source_name_is_valid():
    """
    When dataset_name matches an existing Dataset, source_name is NOT
    required.  The row must be accepted as valid.
    """
    csv_bytes = _build_csv("CP,GDPC,1000,2020,ExistingDataset,,")

    result = parse_and_validate(
        csv_bytes, PROVINCE_MAP, INDICATOR_MAP, EXISTING_DATASET_NAMES
    )

    assert len(result.valid_rows) == 1
    assert result.errors == []


# ---------------------------------------------------------------------------
# Test 6 — Unknown province_code → row error with row_number and raw_value
# REQ-3.1, REQ-12.4
# ---------------------------------------------------------------------------

def test_unknown_province_code_produces_row_error():
    """An unknown province_code must produce a row error citing the raw value."""
    csv_bytes = _build_csv("XX,GDPC,1000,2020,ExistingDataset,,")

    result = parse_and_validate(
        csv_bytes, PROVINCE_MAP, INDICATOR_MAP, EXISTING_DATASET_NAMES
    )

    assert len(result.valid_rows) == 0
    province_errors = [e for e in result.errors if e.column == "province_code"]
    assert len(province_errors) == 1
    err = province_errors[0]
    assert err.row_number == 1
    assert err.raw_value == "XX"


# ---------------------------------------------------------------------------
# Test 7 — Unknown indicator_code → row error
# REQ-3.2, REQ-12.5
# ---------------------------------------------------------------------------

def test_unknown_indicator_code_produces_row_error():
    """An unknown indicator_code must produce a row-level error."""
    csv_bytes = _build_csv("CP,UNKNOWN_IND,1000,2020,ExistingDataset,,")

    result = parse_and_validate(
        csv_bytes, PROVINCE_MAP, INDICATOR_MAP, EXISTING_DATASET_NAMES
    )

    assert any(e.column == "indicator_code" for e in result.errors)
    assert len(result.valid_rows) == 0


# ---------------------------------------------------------------------------
# Test 8 — Non-numeric value → row error
# REQ-3.3, REQ-12.6
# ---------------------------------------------------------------------------

def test_non_numeric_value_produces_row_error():
    """A non-numeric string in the value column must produce a row error."""
    csv_bytes = _build_csv("CP,GDPC,abc,2020,ExistingDataset,,")

    result = parse_and_validate(
        csv_bytes, PROVINCE_MAP, INDICATOR_MAP, EXISTING_DATASET_NAMES
    )

    assert any(e.column == "value" for e in result.errors)
    assert len(result.valid_rows) == 0


# ---------------------------------------------------------------------------
# Test 9 — reference_year=1800 → out-of-range error
# REQ-3.4, REQ-12.7
# ---------------------------------------------------------------------------

def test_reference_year_below_minimum_produces_row_error():
    """reference_year=1800 is below 1900 and must produce a row-level error."""
    csv_bytes = _build_csv("CP,GDPC,1000,1800,ExistingDataset,,")

    result = parse_and_validate(
        csv_bytes, PROVINCE_MAP, INDICATOR_MAP, EXISTING_DATASET_NAMES
    )

    assert any(e.column == "reference_year" for e in result.errors)
    assert len(result.valid_rows) == 0


# ---------------------------------------------------------------------------
# Test 10 — reference_year=2101 → out-of-range error
# REQ-3.4, REQ-12.7
# ---------------------------------------------------------------------------

def test_reference_year_above_maximum_produces_row_error():
    """reference_year=2101 is above 2100 and must produce a row-level error."""
    csv_bytes = _build_csv("CP,GDPC,1000,2101,ExistingDataset,,")

    result = parse_and_validate(
        csv_bytes, PROVINCE_MAP, INDICATOR_MAP, EXISTING_DATASET_NAMES
    )

    assert any(e.column == "reference_year" for e in result.errors)
    assert len(result.valid_rows) == 0


# ---------------------------------------------------------------------------
# Test 11 — Intra-file duplicate natural key → duplicate_row_numbers populated
# REQ-4.1, REQ-4.2, REQ-12.8
# ---------------------------------------------------------------------------

def test_intra_file_duplicate_natural_key():
    """
    Two rows with the same (indicator_code, province_code, reference_year)
    for the same dataset must result in the second row appearing in
    duplicate_row_numbers.  The first row stays in valid_rows.
    """
    csv_bytes = _build_csv(
        "CP,GDPC,1000,2020,ExistingDataset,,",
        "CP,GDPC,9999,2020,ExistingDataset,,",  # same natural key, different value
    )

    result = parse_and_validate(
        csv_bytes, PROVINCE_MAP, INDICATOR_MAP, EXISTING_DATASET_NAMES
    )

    # First occurrence stays valid; second is a duplicate
    assert len(result.valid_rows) == 1
    assert len(result.duplicate_row_numbers) == 1
    assert result.duplicate_row_numbers[0] == 2


# ---------------------------------------------------------------------------
# Test 12 — Binary content → MalformedCsvError raised
# REQ-12.2
# ---------------------------------------------------------------------------

def test_binary_content_raises_malformed_csv_error():
    """Raw binary bytes that cannot be decoded as UTF-8 must raise MalformedCsvError."""
    binary_bytes = bytes(range(256))  # contains non-UTF-8 byte sequences

    with pytest.raises(MalformedCsvError):
        parse_and_validate(
            binary_bytes, PROVINCE_MAP, INDICATOR_MAP, EXISTING_DATASET_NAMES
        )


# ---------------------------------------------------------------------------
# Test 13 — 101 invalid rows → len(errors) == 101 (no truncation in parser)
# REQ-6.6, REQ-6.6b (truncation is service layer responsibility)
# ---------------------------------------------------------------------------

def test_101_invalid_rows_are_all_reported_by_parser():
    """
    The parser must NOT truncate errors.  101 rows all with an unknown
    province_code must produce exactly 101 RowError objects in the result.
    Truncation to 100 is performed by the service layer, not the parser.
    """
    header = "province_code,indicator_code,value,reference_year,dataset_name,source_name,source_url"
    # All rows have "ZZ" — an unknown province_code — to force exactly one error each
    rows = [f"ZZ,GDPC,{i},2020,ExistingDataset,," for i in range(1, 102)]
    csv_content = "\n".join([header, *rows])
    csv_bytes = csv_content.encode("utf-8")

    result = parse_and_validate(
        csv_bytes, PROVINCE_MAP, INDICATOR_MAP, EXISTING_DATASET_NAMES
    )

    assert len(result.errors) == 101
    assert len(result.valid_rows) == 0
