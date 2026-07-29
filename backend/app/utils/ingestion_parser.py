"""
utils/ingestion_parser.py
==========================
Pure, side-effect-free utilities for the ingestion pipeline.

Provides:
  - File format detection (CSV / XLSX)
  - CSV parsing -> ParsedDataset
  - XLSX parsing -> ParsedDataset (with ZIP preflight decompression guard)
  - Column-name normalisation
  - Type inference (INTEGER, DECIMAL, BOOLEAN, DATE, DATETIME, TEXT)
  - Column profiling (missing, unique, nullable, samples)
  - ParsedDataset dataclass -- raw parser result
  - parse_ingestion_file() -- public dispatcher

None of these functions touch the database or raise HTTP exceptions.
Domain exceptions are caught and translated by the service layer.

Exception hierarchy (all names are canonical -- no aliases):
  Exception
  |- FileTooLargeError              file exceeds configured byte limit
  |- UnsupportedFormatError         extension or magic bytes not CSV/XLSX
  |- TooManyRowsError               base row-limit class
  |   `- RowLimitExceededError      file exceeds configured row limit
  |- TooManyColumnsError            base column-limit class
  |   `- ColumnLimitExceededError   file exceeds configured column limit
  `- IngestionParseError            base for all structural parse failures
      |- EmptyDatasetError          no data rows after blank-line filtering
      |- MalformedCSVError          CSV encoding or structural failure
      `- InvalidExcelWorkbookError  XLSX corrupt/encrypted/fails ZIP preflight
"""

from __future__ import annotations

import csv
import io
import math
import re
import zipfile
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal, InvalidOperation

from app.models.data_source import FileFormat
from app.models.ingestion import InferredColumnType


# ---------------------------------------------------------------------------
# Domain exceptions (pure Python -- no FastAPI)
# ---------------------------------------------------------------------------


class IngestionParseError(Exception):
    """Raised for any unrecoverable file parsing failure."""


class FileTooLargeError(Exception):
    """Raised when the file exceeds the configured size limit."""


class TooManyRowsError(Exception):
    """Raised when the file exceeds the configured row-count limit."""


class TooManyColumnsError(Exception):
    """Raised when the file exceeds the configured column-count limit."""


class UnsupportedFormatError(Exception):
    """Raised when the file extension or content is not CSV or XLSX."""


class EmptyDatasetError(IngestionParseError):
    """File contains a header but no data rows (after blank-line filtering)."""


class MalformedCSVError(IngestionParseError):
    """CSV content is structurally malformed (encoding error, quoting, row-width)."""


class InvalidExcelWorkbookError(IngestionParseError):
    """XLSX workbook cannot be opened, is corrupted, or fails ZIP preflight."""


class RowLimitExceededError(TooManyRowsError):
    """File exceeds the configured row-count limit."""


class ColumnLimitExceededError(TooManyColumnsError):
    """File exceeds the configured column-count limit."""


# ---------------------------------------------------------------------------
# Supported formats / magic bytes
# ---------------------------------------------------------------------------

_CSV_EXTENSIONS  = {".csv"}
_XLSX_EXTENSIONS = {".xlsx"}
_XLSX_MAGIC      = b"PK\x03\x04"   # ZIP/XLSX magic bytes


# ---------------------------------------------------------------------------
# ParsedDataset -- raw parser result
# ---------------------------------------------------------------------------


@dataclass
class ParsedDataset:
    """Raw result returned by the parser layer.

    Contains original data only -- no normalisation, no type inference, no profiling.
    Column names are preserved exactly as they appear in the source file (converted
    to str if the library returns non-string headers).
    Row values preserve the native types returned by the parser library:
      CSV  -> all str
      XLSX -> str / int / float / bool / date / datetime / None
    """
    original_column_names: list[str]    # original headers, str, order preserved
    rows: list[list[object]]            # data rows; each maps 1-to-1 with headers
    row_count: int                      # len(rows)
    column_count: int                   # len(original_column_names)
    detected_file_format: FileFormat    # FileFormat.CSV or FileFormat.XLSX
    worksheet_name: str | None          # first worksheet name (XLSX only; None for CSV)


# ---------------------------------------------------------------------------
# File-size guard
# ---------------------------------------------------------------------------


def validate_file_size(content: bytes, max_file_bytes: int) -> None:
    """Raise EmptyDatasetError or FileTooLargeError if byte constraints violated.

    - Zero-byte content -> EmptyDatasetError
    - len(content) > max_file_bytes -> FileTooLargeError
    """
    if len(content) == 0:
        raise EmptyDatasetError("Uploaded file is empty (zero bytes).")
    if len(content) > max_file_bytes:
        raise FileTooLargeError(
            f"File size ({len(content):,} bytes) exceeds the limit of "
            f"{max_file_bytes:,} bytes."
        )


# ---------------------------------------------------------------------------
# Format detection
# ---------------------------------------------------------------------------


def detect_format(filename: str, content: bytes) -> FileFormat:
    """Return FileFormat.CSV or FileFormat.XLSX, or raise UnsupportedFormatError.

    Validates BOTH the declared file extension AND the actual bytes.
    Catches renamed files (XLSX bytes with .csv, or CSV bytes with .xlsx).
    Accepts uppercase extensions via .lower().
    """
    name = filename.lower().strip()
    ext  = "." + name.rsplit(".", 1)[-1] if "." in name else ""

    if ext in _XLSX_EXTENSIONS:
        if content[:4] != _XLSX_MAGIC:
            raise UnsupportedFormatError(
                "File has .xlsx extension but does not appear to be a valid Excel workbook."
            )
        return FileFormat.XLSX

    if ext in _CSV_EXTENSIONS:
        # Catch renamed XLSX files
        if content[:4] == _XLSX_MAGIC:
            raise UnsupportedFormatError(
                "File has .csv extension but appears to be an Excel workbook."
            )
        try:
            content.decode("utf-8-sig")
        except UnicodeDecodeError:
            raise IngestionParseError(
                "File has .csv extension but cannot be decoded as UTF-8 text."
            )
        return FileFormat.CSV

    raise UnsupportedFormatError(
        f"Unsupported file extension '{ext}'. Only .csv and .xlsx are accepted."
    )


# ---------------------------------------------------------------------------
# XLSX ZIP preflight (decompression safety guard)
# ---------------------------------------------------------------------------

# MVP safety limits (parser constants; marked TODO: move to Settings in a later task)
_XLSX_MAX_UNCOMPRESSED_TOTAL_BYTES  = 100 * 1024 * 1024   # 100 MB total uncompressed
_XLSX_MAX_UNCOMPRESSED_MEMBER_BYTES =  50 * 1024 * 1024   # 50 MB per member
_XLSX_MAX_MEMBER_COUNT              = 1_000                # max ZIP entries
_XLSX_MAX_COMPRESSION_RATIO         = 100                  # max ratio per member


def _xlsx_zip_preflight(content: bytes) -> None:
    """Inspect XLSX ZIP archive metadata WITHOUT extracting any content.

    Raises InvalidExcelWorkbookError for:
    - Content that is not a valid ZIP archive
    - Encrypted (password-protected) ZIP members
    - Archive members with suspicious paths (absolute paths or '..' traversal)
    - Total uncompressed size > _XLSX_MAX_UNCOMPRESSED_TOTAL_BYTES
    - Any single member uncompressed size > _XLSX_MAX_UNCOMPRESSED_MEMBER_BYTES
    - Member count > _XLSX_MAX_MEMBER_COUNT
    - Compression ratio of any member > _XLSX_MAX_COMPRESSION_RATIO

    Does NOT extract any content to disk or memory.
    Does NOT reveal archive member names or paths in client-facing messages.
    openpyxl must only be called AFTER this preflight succeeds.
    """
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as zf:
            members = zf.infolist()

            if len(members) > _XLSX_MAX_MEMBER_COUNT:
                raise InvalidExcelWorkbookError(
                    "Workbook archive exceeds the maximum number of entries."
                )

            total_uncompressed = 0
            for info in members:
                # Encrypted member detection
                if info.flag_bits & 0x1:
                    raise InvalidExcelWorkbookError(
                        "Workbook appears to be password-protected or encrypted."
                    )

                # Suspicious path: absolute or parent traversal
                name = info.filename
                parts = name.replace("\\", "/").split("/")
                if name.startswith("/") or ".." in parts:
                    raise InvalidExcelWorkbookError(
                        "Workbook contains an entry with a suspicious path."
                    )

                # Per-member uncompressed size
                if info.file_size > _XLSX_MAX_UNCOMPRESSED_MEMBER_BYTES:
                    raise InvalidExcelWorkbookError(
                        "Workbook contains an entry that exceeds the maximum uncompressed size."
                    )

                # Compression ratio (avoid divide-by-zero)
                if info.compress_size > 0:
                    ratio = info.file_size / info.compress_size
                    if ratio > _XLSX_MAX_COMPRESSION_RATIO:
                        raise InvalidExcelWorkbookError(
                            "Workbook contains an entry with a suspicious compression ratio."
                        )

                total_uncompressed += info.file_size

            if total_uncompressed > _XLSX_MAX_UNCOMPRESSED_TOTAL_BYTES:
                raise InvalidExcelWorkbookError(
                    "Workbook archive exceeds the maximum total uncompressed size."
                )

    except zipfile.BadZipFile as exc:
        raise InvalidExcelWorkbookError("File is not a valid ZIP/XLSX archive.") from exc
    except InvalidExcelWorkbookError:
        raise
    except Exception as exc:
        raise InvalidExcelWorkbookError("Workbook archive could not be inspected.") from exc


# ---------------------------------------------------------------------------
# CSV parser -- returns ParsedDataset
# ---------------------------------------------------------------------------


def parse_csv(
    content: bytes,
    *,
    max_rows: int,
    max_columns: int,
) -> ParsedDataset:
    """Parse CSV bytes into a raw ParsedDataset.

    Encoding:
    - Decoded with utf-8-sig (handles UTF-8 BOM transparently).
    - UnicodeDecodeError -> MalformedCSVError (no raw content in message).

    Blank-line rule (documented):
    - Rows where every cell after .strip() is empty are silently skipped.
    - Blank rows do NOT count toward the row limit.
    - A row with at least one non-blank cell is a data row and must match header width.

    Row-limit semantics:
    - Exactly max_rows rows succeed; max_rows+1 rows raise RowLimitExceededError.

    All row values are strings (CSV is always text).
    worksheet_name is None for CSV.
    detected_file_format is FileFormat.CSV.
    """
    try:
        text_content = content.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise MalformedCSVError("CSV file cannot be decoded as UTF-8.") from exc

    if not text_content.strip():
        raise EmptyDatasetError("Uploaded CSV file is empty.")

    reader = csv.reader(io.StringIO(text_content))
    try:
        raw_headers = next(reader)
    except StopIteration:
        raise MalformedCSVError("CSV file has no header row.")

    if not any(h.strip() for h in raw_headers):
        raise MalformedCSVError("CSV header row contains only blank columns.")

    headers = raw_headers  # preserve original header strings exactly

    if len(headers) > max_columns:
        raise ColumnLimitExceededError(
            f"File has {len(headers)} columns; the limit is {max_columns}."
        )

    expected  = len(headers)
    rows: list[list[object]] = []
    row_number = 0

    try:
        for raw_row in reader:
            row_number += 1
            # Blank-line rule: skip rows where every cell is blank after strip
            if not any(cell.strip() for cell in raw_row):
                continue

            # Row-width validation
            if len(raw_row) != expected:
                raise MalformedCSVError(
                    f"Row {row_number} has {len(raw_row)} fields; expected {expected}."
                )

            rows.append(list(raw_row))

            # Row-limit: exactly max_rows succeed; max_rows+1 fails
            if len(rows) >= max_rows:
                for next_raw in reader:
                    if any(cell.strip() for cell in next_raw):
                        raise RowLimitExceededError(
                            f"File exceeds the row limit of {max_rows:,} rows."
                        )
                break
    except (MalformedCSVError, RowLimitExceededError, ColumnLimitExceededError):
        raise
    except csv.Error as exc:
        raise MalformedCSVError("Malformed CSV content detected.") from exc

    if len(rows) == 0:
        raise EmptyDatasetError("CSV file has a header but no data rows.")

    return ParsedDataset(
        original_column_names=headers,
        rows=rows,
        row_count=len(rows),
        column_count=len(headers),
        detected_file_format=FileFormat.CSV,
        worksheet_name=None,
    )


# ---------------------------------------------------------------------------
# XLSX parser -- returns ParsedDataset
# ---------------------------------------------------------------------------


def parse_xlsx(
    content: bytes,
    *,
    max_rows: int,
    max_columns: int,
) -> ParsedDataset:
    """Parse XLSX bytes into a raw ParsedDataset.

    Header-row rule (documented):
    - Physical row 1 is always the header row regardless of content.
    - Trailing None/empty-string header cells are trimmed to get logical column width.
    - A None header cell in a non-trailing position is preserved as "".

    Blank-row rule (documented):
    - Data rows where every cell is None are silently skipped.
    - Blank rows do NOT count toward the row limit.

    Short rows are padded with None to match header width.
    Rows wider than the logical header (after trimming trailing None) raise MalformedCSVError.

    Row-limit: exactly max_rows succeed; max_rows+1 raises RowLimitExceededError.

    Native cell types preserved: str, int, float, bool, date, datetime, None.
    ZIP preflight runs before openpyxl is invoked.
    """
    import openpyxl  # local import

    # ZIP preflight BEFORE opening with openpyxl
    _xlsx_zip_preflight(content)

    wb = None
    try:
        try:
            wb = openpyxl.load_workbook(
                io.BytesIO(content),
                read_only=True,
                data_only=True,
            )
        except InvalidExcelWorkbookError:
            raise
        except Exception as exc:
            raise InvalidExcelWorkbookError("Could not open workbook.") from exc

        if not wb.worksheets:
            raise InvalidExcelWorkbookError("Workbook has no worksheets.")

        ws = wb.worksheets[0]           # first worksheet; more explicit than .active
        worksheet_name: str | None = ws.title

        rows_iter = ws.iter_rows(values_only=True)

        # Physical row 1 is always the header
        try:
            raw_header_tuple = next(rows_iter)
        except StopIteration:
            raise EmptyDatasetError("Excel worksheet is empty.")

        # Convert each header cell to str; None -> ""
        raw_headers: list[str] = [
            str(cell) if cell is not None else ""
            for cell in raw_header_tuple
        ]

        # Trim trailing empty headers to get logical column width
        headers = raw_headers.copy()
        while headers and headers[-1].strip() == "":
            headers.pop()

        # Restore if all blank so we can raise correctly
        if not headers:
            headers = raw_headers

        if not any(h.strip() for h in headers):
            raise InvalidExcelWorkbookError("Excel header row contains only blank columns.")

        if len(headers) > max_columns:
            raise ColumnLimitExceededError(
                f"File has {len(headers)} columns; the limit is {max_columns}."
            )

        expected = len(headers)
        rows: list[list[object]] = []

        for row_idx, raw_row in enumerate(rows_iter, start=1):
            # Blank row: all cells None -> skip silently
            if all(cell is None for cell in raw_row):
                continue

            row_list = list(raw_row)

            # Trim trailing None to determine actual data width
            trimmed = row_list.copy()
            while trimmed and trimmed[-1] is None:
                trimmed.pop()

            if len(trimmed) > expected:
                raise MalformedCSVError(
                    f"Row {row_idx} has {len(trimmed)} fields beyond header width {expected}."
                )

            # Pad/trim to exactly expected width
            if len(row_list) < expected:
                row_list.extend([None] * (expected - len(row_list)))
            else:
                row_list = row_list[:expected]

            rows.append(row_list)

            # Row-limit: exactly max_rows succeed; max_rows+1 fails
            if len(rows) >= max_rows:
                for next_raw in rows_iter:
                    if not all(cell is None for cell in next_raw):
                        raise RowLimitExceededError(
                            f"File exceeds the row limit of {max_rows:,} rows."
                        )
                break

        if len(rows) == 0:
            raise EmptyDatasetError("Excel worksheet has a header but no data rows.")

        return ParsedDataset(
            original_column_names=headers,
            rows=rows,
            row_count=len(rows),
            column_count=len(headers),
            detected_file_format=FileFormat.XLSX,
            worksheet_name=worksheet_name,
        )

    finally:
        if wb is not None:
            try:
                wb.close()
            except Exception:
                pass


# ---------------------------------------------------------------------------
# parse_ingestion_file -- public dispatcher
# ---------------------------------------------------------------------------


def parse_ingestion_file(
    filename: str,
    content: bytes,
    *,
    max_file_bytes: int,
    max_rows: int,
    max_columns: int,
) -> ParsedDataset:
    """Parse a CSV or XLSX upload into a raw ParsedDataset.

    1. Validate file size (empty -> EmptyDatasetError, too large -> FileTooLargeError).
    2. Detect format from filename extension + content bytes.
    3. Dispatch to parse_csv or parse_xlsx.
    4. Return ParsedDataset (no normalisation, inference, or profiling).

    No raw content, file paths, or library internals appear in exception messages.
    """
    validate_file_size(content, max_file_bytes)
    fmt = detect_format(filename, content)
    if fmt == FileFormat.CSV:
        return parse_csv(content, max_rows=max_rows, max_columns=max_columns)
    return parse_xlsx(content, max_rows=max_rows, max_columns=max_columns)


# ---------------------------------------------------------------------------
# Missing-value detection
# ---------------------------------------------------------------------------


def is_missing_value(value: object) -> bool:
    """Return True if value represents a missing/null entry.

    Rules:
    - None -> True
    - "" -> True
    - strings that are only whitespace -> True
    - float("nan") -> True
    - pandas NaT and NA (if pandas installed) -> True
    - 0, 0.0, False, "0", "false" -> False
    """
    if value is None:
        return True
    if isinstance(value, float) and math.isnan(value):
        return True
    if isinstance(value, str):
        return value.strip() == ""
    try:
        import pandas as pd  # noqa: PLC0415
        if isinstance(value, type(pd.NaT)) or value is pd.NA:
            return True
    except ImportError:
        pass
    return False


# ---------------------------------------------------------------------------
# Sample value serialisation
# ---------------------------------------------------------------------------


def serialize_sample_value(value: object, max_length: int = 200) -> object:
    """Return a JSON-compatible representation of *value*. Never raises.

    Precedence:
    1. Missing values -> None
    2. bool (before int) -> as-is
    3. int -> as-is
    4. float NaN/Inf -> None; otherwise float as-is
    5. Decimal -> str(value) (preserves "12.50" exactly)
    6. datetime -> value.isoformat()
    7. date (not datetime) -> value.strftime("%Y-%m-%d")
    8. str -> truncate to max_length
    9. fallback -> str(value)[:max_length]
    """
    try:
        if is_missing_value(value):
            return None
        if isinstance(value, bool):
            return value
        if isinstance(value, int):
            return value
        if isinstance(value, float):
            if math.isnan(value) or math.isinf(value):
                return None
            return value
        if isinstance(value, Decimal):
            return str(value)
        if isinstance(value, datetime):
            return value.isoformat()
        if isinstance(value, date):
            return value.strftime("%Y-%m-%d")
        if isinstance(value, str):
            return value[:max_length]
        return str(value)[:max_length]
    except Exception:  # noqa: BLE001
        return None


# ---------------------------------------------------------------------------
# Column-name normalisation
# ---------------------------------------------------------------------------


def normalize_column_name(value: object) -> str:
    """Normalise a single column name deterministically.

    Rules:
    1. Convert to str (None -> "").
    2. Strip surrounding whitespace.
    3. Lowercase.
    4. Replace any non-alphanumeric run with a single underscore.
    5. Remove leading/trailing underscores.
    6. Empty/punctuation-only input -> "column".

    Idempotent: normalize_column_name(normalize_column_name(x)) == normalize_column_name(x).
    """
    s = str(value) if value is not None else ""
    s = s.strip().lower()
    s = re.sub(r"[^a-z0-9]+", "_", s)
    s = s.strip("_")
    return s or "column"


def normalize_column_names(original_names: Sequence[object]) -> list[str]:
    """Normalise a list of column names, ensuring uniqueness.

    Duplicate normalised names get a numeric suffix: value, value_2, value_3, ...
    The deduplication loop keeps incrementing until a unique candidate is found,
    handling the case where a generated suffix itself collides with another name.
    """
    seen: set[str] = set()
    result: list[str] = []
    for name in original_names:
        base = normalize_column_name(name)
        if base not in seen:
            seen.add(base)
            result.append(base)
        else:
            counter = 2
            candidate = f"{base}_{counter}"
            while candidate in seen:
                counter += 1
                candidate = f"{base}_{counter}"
            seen.add(candidate)
            result.append(candidate)
    return result


# ---------------------------------------------------------------------------
# Type inference
# ---------------------------------------------------------------------------

# Boolean tokens -- strictly {"true","false","yes","no"} only.
# Numeric aliases ("1","0") and single-letter aliases are intentionally excluded
# so that numeric columns infer INTEGER, not BOOLEAN.
_BOOL_TRUE  = {"true", "yes"}
_BOOL_FALSE = {"false", "no"}
_BOOL_ALL   = _BOOL_TRUE | _BOOL_FALSE

# Unambiguous date/datetime patterns
_RE_DATE = re.compile(
    r"^\d{4}(-(?:0[1-9]|1[0-2])-(?:0[1-9]|[12]\d|3[01])|"
    r"/(?:0[1-9]|1[0-2])/(?:0[1-9]|[12]\d|3[01]))$"
)
_RE_DATETIME = re.compile(
    r"^\d{4}-(?:0[1-9]|1[0-2])-(?:0[1-9]|[12]\d|3[01])[T ]\d{2}:\d{2}"
    r"(?::\d{2})?(?:Z|[+-]\d{2}:\d{2})?$"
)
_RE_LEADING_ZERO = re.compile(r"^0\d+$")
_RE_CURRENCY     = re.compile(r"[£$€¥₹₦]")
_INFINITY_STRINGS = {"inf", "-inf", "infinity", "-infinity", "nan"}


def _is_integer(v: str) -> bool:
    v = v.strip()
    if _RE_LEADING_ZERO.match(v):
        return False
    if _RE_CURRENCY.search(v):
        return False
    if v.lower() in _INFINITY_STRINGS:
        return False
    if "," in v:
        return False
    try:
        int(v)
        return True
    except ValueError:
        return False


def _is_decimal(v: str) -> bool:
    v = v.strip()
    parts = v.split(".")
    if _RE_LEADING_ZERO.match(parts[0].lstrip("-+")):
        return False
    if _RE_CURRENCY.search(v):
        return False
    if v.lower() in _INFINITY_STRINGS:
        return False
    if "," in v:
        return False
    try:
        d = Decimal(v)
        if not d.is_finite():
            return False
        if "." not in v and "e" not in v.lower():
            return False
        return True
    except InvalidOperation:
        return False


def _is_boolean(v: str) -> bool:
    return v.lower() in _BOOL_ALL


def _is_date(v: str) -> bool:
    return bool(_RE_DATE.match(v))


def _is_datetime(v: str) -> bool:
    return bool(_RE_DATETIME.match(v))


def infer_column_type(values: Iterable[object]) -> InferredColumnType:
    """Infer the column type from a collection of values.

    Missing values (None, "", whitespace, NaN) are ignored.
    If no non-missing values exist, returns TEXT.
    Mixed or ambiguous values fall back to TEXT.
    Source values are NEVER mutated.

    Type-test order:
      BOOLEAN  -> exact strings "true"/"false"/"yes"/"no" (case-insensitive)
      INTEGER  -> parses as int, no leading zeros, no commas, no currency
      DECIMAL  -> parses as Decimal with "." or "e", no Inf/NaN, no commas
      DATETIME -> ISO 8601 datetime string
      DATE     -> YYYY-MM-DD or YYYY/MM/DD (consistent separator)
      TEXT     -> fallback

    Scientific notation ("1.5e10") infers DECIMAL (has "e", passes Decimal()).
    Python bool objects always infer BOOLEAN (caught before string tests).
    """
    non_missing = [v for v in values if not is_missing_value(v)]
    if not non_missing:
        return InferredColumnType.TEXT

    if all(isinstance(v, bool) for v in non_missing):
        return InferredColumnType.BOOLEAN

    str_values = [str(v).strip() for v in non_missing]

    for test_fn, col_type in [
        (_is_boolean,  InferredColumnType.BOOLEAN),
        (_is_integer,  InferredColumnType.INTEGER),
        (_is_decimal,  InferredColumnType.DECIMAL),
        (_is_datetime, InferredColumnType.DATETIME),
        (_is_date,     InferredColumnType.DATE),
    ]:
        if all(test_fn(v) for v in str_values):
            return col_type

    return InferredColumnType.TEXT


# ---------------------------------------------------------------------------
# Column profiling
# ---------------------------------------------------------------------------

_SAMPLE_MAX_LEN = 200
_SAMPLE_COUNT   = 5


@dataclass
class ColumnProfile:
    original_name: str
    normalized_name: str
    inferred_type: InferredColumnType
    missing_count: int
    unique_count: int
    nullable: bool
    sample_values: list


def profile_column(original_name: str, normalized_name: str, values: list) -> ColumnProfile:
    """Compute profiling statistics for a single column."""
    missing     = sum(1 for v in values if is_missing_value(v))
    non_missing = [v for v in values if not is_missing_value(v)]
    unique      = len(set(str(v) for v in non_missing))
    nullable    = missing > 0
    inferred    = infer_column_type(values)

    seen_strs: set[str] = set()
    samples: list = []
    for v in non_missing:
        key = str(v)
        if key not in seen_strs:
            seen_strs.add(key)
            serialised = serialize_sample_value(v)
            if serialised is not None:
                samples.append(serialised)
        if len(samples) >= _SAMPLE_COUNT:
            break

    return ColumnProfile(
        original_name=original_name,
        normalized_name=normalized_name,
        inferred_type=inferred,
        missing_count=missing,
        unique_count=unique,
        nullable=nullable,
        sample_values=samples,
    )
