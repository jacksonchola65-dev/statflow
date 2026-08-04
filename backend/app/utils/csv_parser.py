"""
csv_parser.py
=============
Pure CSV parser and row-level validator for the StatFlow import pipeline.

Design constraints
------------------
- No database access, no filesystem writes, no network calls.
- No FastAPI, SQLAlchemy, or Pydantic imports — framework-agnostic.
- All lookup data is passed in as plain Python dicts/sets.
- Errors are NOT capped here; the service layer applies the 100-item cap.
- Row numbers are 1-based (header row = 0, first data row = 1).

Public API
----------
parse_and_validate(
    raw_bytes:              bytes,
    province_map:           dict[str, UUID],   # code.upper() → province UUID
    indicator_map:          dict[str, UUID],   # code.upper() → indicator UUID
    existing_dataset_names: set[str],          # names of Datasets already in DB
) -> ParseResult

Raises
------
MalformedCsvError   — file cannot be decoded or parsed as CSV
MissingColumnsError — one or more required columns absent from header
EmptyFileError      — zero bytes or header-only with no data rows
RowLimitExceeded    — more than MAX_DATA_ROWS non-empty data rows
"""

from __future__ import annotations

import csv
import io
import uuid
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import cast

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

REQUIRED_COLUMNS: tuple[str, ...] = (
    "province_code",
    "indicator_code",
    "value",
    "reference_year",
    "dataset_name",
)

OPTIONAL_COLUMNS: tuple[str, ...] = (
    "source_name",
    "source_url",
)

REFERENCE_YEAR_MIN = 1900
REFERENCE_YEAR_MAX = 2100

MAX_DATA_ROWS = 10_000

# Sniff at most this many bytes to detect the delimiter
_SNIFF_BYTES = 4096

# ---------------------------------------------------------------------------
# Custom exceptions  (no FastAPI / HTTP awareness)
# ---------------------------------------------------------------------------


class CsvParserError(Exception):
    """Base class for all errors raised before row-level processing begins."""


class EmptyFileError(CsvParserError):
    """Raised when the uploaded bytes are empty or contain only a header row."""


class MalformedCsvError(CsvParserError):
    """Raised when the bytes cannot be decoded as UTF-8 or parsed as CSV."""


class MissingColumnsError(CsvParserError):
    """Raised when one or more required columns are absent from the header."""

    def __init__(self, missing: list[str]) -> None:
        self.missing = missing
        super().__init__(f"Missing required columns: {missing}")


class RowLimitExceeded(CsvParserError):
    """Raised when the file contains more than MAX_DATA_ROWS non-empty rows."""

    def __init__(self, count: int) -> None:
        self.count = count
        super().__init__(
            f"File contains {count} data rows, which exceeds the {MAX_DATA_ROWS} row limit."
        )


# ---------------------------------------------------------------------------
# Data transfer objects
# ---------------------------------------------------------------------------


@dataclass
class ParsedRow:
    """A single data row that passed all validation checks."""

    row_number: int  # 1-based index in the CSV (header = 0)
    province_id: uuid.UUID
    indicator_id: uuid.UUID
    value: Decimal
    reference_year: int
    dataset_name: str  # always present (required column)
    source_name: str | None  # None when dataset already exists in DB
    source_url: str | None

    # Human-readable codes kept for use in SampleRecordSchema
    province_code: str
    indicator_code: str


@dataclass
class RowError:
    """A validation failure on a single cell within a data row."""

    row_number: int  # 1-based
    column: str  # CSV column name that failed
    raw_value: str  # exact cell content (stripped of surrounding whitespace)
    message: str  # human-readable description


@dataclass
class ParseResult:
    """
    Aggregate result returned by parse_and_validate.

    valid_rows        — rows that passed every validation check
    errors            — ALL row-level errors (NOT capped; service caps at 100)
    duplicate_row_numbers
                      — row_number values of rows whose natural key
                        (indicator_id, province_id, reference_year)
                        appeared more than once within the file.
                        Only the second and subsequent occurrences are listed;
                        the first occurrence is kept in valid_rows.
    """

    valid_rows: list[ParsedRow] = field(default_factory=list)
    errors: list[RowError] = field(default_factory=list)
    duplicate_row_numbers: list[int] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _decode_bytes(raw_bytes: bytes) -> str:
    """Decode raw bytes as UTF-8.  Raises MalformedCsvError on failure."""
    try:
        return raw_bytes.decode("utf-8")
    except (UnicodeDecodeError, ValueError) as exc:
        raise MalformedCsvError(f"File could not be decoded as UTF-8: {exc}") from exc


def _detect_dialect(text: str) -> csv.Dialect:
    """
    Try csv.Sniffer on the first _SNIFF_BYTES characters.
    Fall back to excel (comma-delimited) if sniffing fails.
    """
    sample = text[:_SNIFF_BYTES]
    try:
        return cast(csv.Dialect, csv.Sniffer().sniff(sample, delimiters=",;\t|"))
    except csv.Error:
        return csv.excel()


def _normalise_header(raw_headers: list[str]) -> list[str]:
    """Strip whitespace and lower-case every header name."""
    return [h.strip().lower() for h in raw_headers]


def _check_required_columns(headers: list[str]) -> None:
    """Raise MissingColumnsError if any required column is absent."""
    missing = [c for c in REQUIRED_COLUMNS if c not in headers]
    if missing:
        raise MissingColumnsError(missing)


def _is_blank_row(row: dict[str, str]) -> bool:
    """Return True if every cell in the row is empty after stripping."""
    return all(v.strip() == "" for v in row.values())


def _strip_row(row: dict[str, str]) -> dict[str, str]:
    """Return a new dict with all values stripped of surrounding whitespace."""
    return {k: v.strip() for k, v in row.items()}


def _validate_row(
    row: dict[str, str],
    row_number: int,
    province_map: dict[str, uuid.UUID],
    indicator_map: dict[str, uuid.UUID],
    existing_dataset_names: set[str],
) -> tuple[ParsedRow | None, list[RowError]]:
    """
    Validate a single stripped data row.

    Returns (ParsedRow, []) on success or (None, [RowError, ...]) on failure.
    All errors for the row are collected before returning.
    """
    errors: list[RowError] = []

    # -- province_code -------------------------------------------------------
    raw_province = row.get("province_code", "")
    province_id: uuid.UUID | None = province_map.get(raw_province.upper())
    if not raw_province:
        errors.append(
            RowError(row_number, "province_code", raw_province, "province_code is required.")
        )
    elif province_id is None:
        errors.append(
            RowError(
                row_number,
                "province_code",
                raw_province,
                f"Unknown province_code: '{raw_province}'.",
            )
        )

    # -- indicator_code ------------------------------------------------------
    raw_indicator = row.get("indicator_code", "")
    indicator_id: uuid.UUID | None = indicator_map.get(raw_indicator.upper())
    if not raw_indicator:
        errors.append(
            RowError(row_number, "indicator_code", raw_indicator, "indicator_code is required.")
        )
    elif indicator_id is None:
        errors.append(
            RowError(
                row_number,
                "indicator_code",
                raw_indicator,
                f"Unknown indicator_code: '{raw_indicator}'.",
            )
        )

    # -- value ---------------------------------------------------------------
    raw_value = row.get("value", "")
    parsed_value: Decimal | None = None
    if not raw_value:
        errors.append(RowError(row_number, "value", raw_value, "value is required."))
    else:
        try:
            parsed_value = Decimal(raw_value)
            if not parsed_value.is_finite():
                raise InvalidOperation
        except InvalidOperation:
            errors.append(
                RowError(
                    row_number,
                    "value",
                    raw_value,
                    f"value must be a finite number; got '{raw_value}'.",
                )
            )
            parsed_value = None

    # -- reference_year ------------------------------------------------------
    raw_year = row.get("reference_year", "")
    parsed_year: int | None = None
    if not raw_year:
        errors.append(
            RowError(row_number, "reference_year", raw_year, "reference_year is required.")
        )
    else:
        try:
            parsed_year = int(raw_year)
            if parsed_year < REFERENCE_YEAR_MIN or parsed_year > REFERENCE_YEAR_MAX:
                errors.append(
                    RowError(
                        row_number,
                        "reference_year",
                        raw_year,
                        f"reference_year must be between {REFERENCE_YEAR_MIN} "
                        f"and {REFERENCE_YEAR_MAX}; got {parsed_year}.",
                    )
                )
                parsed_year = None
        except ValueError:
            errors.append(
                RowError(
                    row_number,
                    "reference_year",
                    raw_year,
                    f"reference_year must be an integer; got '{raw_year}'.",
                )
            )
            parsed_year = None

    # -- dataset_name --------------------------------------------------------
    raw_dataset = row.get("dataset_name", "")
    if not raw_dataset:
        errors.append(
            RowError(
                row_number,
                "dataset_name",
                raw_dataset,
                "dataset_name is required and must not be blank.",
            )
        )

    # -- source_name (conditional) -------------------------------------------
    # Required only when dataset_name is non-empty AND not in existing_dataset_names
    raw_source_name = row.get("source_name", "")
    if (
        raw_dataset  # dataset_name present and non-empty
        and raw_dataset not in existing_dataset_names
        and not raw_source_name
    ):
        errors.append(
            RowError(
                row_number,
                "source_name",
                raw_source_name,
                f"source_name is required when dataset_name '{raw_dataset}' "
                "does not match an existing dataset.",
            )
        )

    # -- source_url (always optional) ----------------------------------------
    raw_source_url = row.get("source_url", "") or None  # treat blank as None

    # -- Return early if any error collected ---------------------------------
    if errors:
        return None, errors

    # All fields valid — build the ParsedRow
    assert province_id is not None
    assert indicator_id is not None
    assert parsed_value is not None
    assert parsed_year is not None

    parsed_row = ParsedRow(
        row_number=row_number,
        province_id=province_id,
        indicator_id=indicator_id,
        value=parsed_value,
        reference_year=parsed_year,
        dataset_name=raw_dataset,
        source_name=raw_source_name or None,
        source_url=raw_source_url,
        province_code=raw_province,
        indicator_code=raw_indicator,
    )
    return parsed_row, []


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def parse_and_validate(
    raw_bytes: bytes,
    province_map: dict[str, uuid.UUID],
    indicator_map: dict[str, uuid.UUID],
    existing_dataset_names: set[str],
) -> ParseResult:
    """
    Parse and validate a CSV file supplied as raw bytes.

    Parameters
    ----------
    raw_bytes
        The uploaded file content.  Must be UTF-8 encoded.
    province_map
        Mapping of upper-cased province code → province UUID.
        Example: {"CP": UUID("…"), "LK": UUID("…")}
    indicator_map
        Mapping of upper-cased indicator code → indicator UUID.
    existing_dataset_names
        Set of Dataset.name values already present in the database.
        Used to determine whether source_name is required.

    Returns
    -------
    ParseResult
        Contains valid_rows, errors (ALL of them — not capped), and
        duplicate_row_numbers.

    Raises
    ------
    EmptyFileError       if raw_bytes is empty.
    MalformedCsvError    if decoding or CSV parsing fails.
    MissingColumnsError  if a required column is absent.
    RowLimitExceeded     if there are more than MAX_DATA_ROWS data rows.
    """
    # Guard: empty file
    if not raw_bytes:
        raise EmptyFileError("Uploaded file is empty.")

    # Decode
    text = _decode_bytes(raw_bytes)

    # Guard: try to parse with sniffed dialect, fall back to excel
    dialect = _detect_dialect(text)
    try:
        # Read only fieldnames — do not iterate yet.
        probe = csv.DictReader(io.StringIO(text), dialect=dialect)
        raw_fieldnames = probe.fieldnames
    except csv.Error as exc:
        raise MalformedCsvError(f"CSV parsing failed: {exc}") from exc

    # Validate fieldnames were detected
    if not raw_fieldnames:
        raise MalformedCsvError("CSV file has no header row.")

    # Normalise header names (strip + lower-case)
    normalised_headers = _normalise_header(list(raw_fieldnames))

    # Use normalised fieldnames directly with DictReader on the original text.
    # This avoids rebuilding and reparsing the entire CSV — DictReader accepts
    # an explicit fieldnames list and skips the first row as the header.
    _check_required_columns(normalised_headers)

    # Re-create the reader on the original text, injecting normalised names.
    # skip_initial_space is preserved from the sniffed dialect.
    try:
        normalised_reader = csv.DictReader(
            io.StringIO(text),
            fieldnames=normalised_headers,
            dialect=dialect,
        )
        # Advance past the original header row (which is now treated as a data row
        # because we supplied explicit fieldnames).
        next(normalised_reader)
    except (csv.Error, StopIteration) as exc:
        raise MalformedCsvError(f"CSV parsing failed during header skip: {exc}") from exc

    # Collect all data rows
    result = ParseResult()
    # Natural key includes dataset_name (normalised) so rows for different
    # datasets with the same indicator+province+year are not flagged as duplicates.
    seen_natural_keys: dict[tuple[str, uuid.UUID, uuid.UUID, int], int] = {}
    data_row_count = 0

    for raw_row in normalised_reader:
        # Skip blank rows
        if _is_blank_row(raw_row):
            continue

        data_row_count += 1

        # Enforce row limit
        if data_row_count > MAX_DATA_ROWS:
            raise RowLimitExceeded(data_row_count)

        # Row number = 1-based data row index (header is row 0)
        row_number = data_row_count

        stripped = _strip_row(raw_row)

        parsed_row, errors = _validate_row(
            stripped, row_number, province_map, indicator_map, existing_dataset_names
        )

        if errors:
            result.errors.extend(errors)
        else:
            assert parsed_row is not None
            # Duplicate detection: (normalised_dataset_name, indicator_id, province_id, reference_year)
            # Normalise dataset_name for comparison: strip + lower-case.
            # The original trimmed value is preserved in ParsedRow.dataset_name.
            natural_key = (
                parsed_row.dataset_name.strip().lower(),
                parsed_row.indicator_id,
                parsed_row.province_id,
                parsed_row.reference_year,
            )
            if natural_key in seen_natural_keys:
                result.duplicate_row_numbers.append(parsed_row.row_number)
            else:
                seen_natural_keys[natural_key] = parsed_row.row_number
                result.valid_rows.append(parsed_row)

    return result
