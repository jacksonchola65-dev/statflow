"""
services/ingestion_profiling_service.py
=========================================
In-memory ingestion profiling service.

Transforms raw uploaded file bytes into a fully validated, typed
IngestionProfileResult — without touching the database.

Pipeline
--------
1. Parse       — parse_ingestion_file()   → ParsedDataset
2. Normalize   — normalize_column_names() → list[str]
3. Profile     — infer_column_type(), is_missing_value(), serialize_sample_value()
4. Row convert — _convert_cell() + serialize_row_values()
5. Validate    — consistency checks before returning

Dependencies (all pre-existing — no logic duplicated here):
    parse_ingestion_file()   — CSV/XLSX parsing
    normalize_column_names() — deterministic header normalisation
    infer_column_type()      — per-column type inference
    is_missing_value()       — missing-cell detection
    serialize_sample_value() — safe per-value serialization for samples
    serialize_row_values()   — full row dict serialization
    validate_row_values()    — post-serialization validation

Design constraints
------------------
- Pure function — no DB access, no repositories, no ORM models, no HTTP.
- Obtains ingestion limits from Settings rather than from callers.
- All parser/serializer exceptions are wrapped in IngestionProfilingError.

Memory note
-----------
Memory usage grows approximately linearly with row count and is bounded
by the configured parser limits (INGESTION_MAX_ROWS, INGESTION_MAX_COLUMNS).
The profiling service holds all parsed rows in memory simultaneously during
processing. Streaming ingestion is deferred to a future milestone.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from app.core.config import settings
from app.models.data_source import FileFormat
from app.models.ingestion import InferredColumnType
from app.utils.ingestion_parser import (
    IngestionParseError,
    is_missing_value,
    normalize_column_names,
    parse_ingestion_file,
    serialize_sample_value,
)
from app.utils.row_values import RowValuesError, serialize_row_values

# ---------------------------------------------------------------------------
# Sample limit
# ---------------------------------------------------------------------------

_SAMPLE_LIMIT: int = 5   # maximum representative sample values per column

# ---------------------------------------------------------------------------
# Service exception
# ---------------------------------------------------------------------------


class IngestionProfilingError(Exception):
    """Raised when the profiling pipeline fails for any reason.

    The original exception is always preserved as __cause__ via `raise ... from`.
    """


# ---------------------------------------------------------------------------
# Typed result models
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ProfiledColumn:
    """Per-column metadata produced during profiling.

    ordinal_position is zero-based, matching the left-to-right column
    order in the source file.
    """
    ordinal_position: int
    original_name:    str
    normalized_name:  str
    inferred_type:    InferredColumnType
    nullable:         bool
    missing_count:    int
    unique_count:     int
    sample_values:    list[Any]   # up to _SAMPLE_LIMIT serialized values


@dataclass(frozen=True)
class ProfiledRow:
    """A single normalized data row."""
    row_number: int
    values:     dict[str, Any]   # normalized_name → JSON-compatible value


@dataclass(frozen=True)
class IngestionProfileResult:
    """Complete in-memory ingestion profile returned by profile_dataset()."""
    original_filename:    str
    detected_file_format: FileFormat
    worksheet_name:       str | None
    row_count:            int
    column_count:         int
    columns:              list[ProfiledColumn]
    rows:                 list[ProfiledRow]


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _convert_cell(col_name: str, value: Any) -> Any:
    """Convert a raw parser cell value to a JSON-compatible scalar.

    Uses serialize_sample_value() for date/datetime/Decimal/None handling,
    then delegates to _serialize_scalar logic via serialize_row_values.

    Dates and datetimes are converted to ISO strings here so that the
    downstream serialize_row_values() receives only str/int/float/bool/None.

    Raises IngestionProfilingError if the value cannot be serialized.
    """
    # Handle missing first
    if is_missing_value(value):
        return None

    # date/datetime → ISO string (serialize_row_values doesn't handle these)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.strftime("%Y-%m-%d")

    # Decimal → str (exact canonical representation, no precision loss).
    # Centralized in row_values._serialize_scalar — handled there via
    # serialize_row_values(). This pre-conversion is kept here only for
    # date/datetime, which row_values doesn't handle.
    # Decimal is NOT converted here; it passes through to serialize_row_values().
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise IngestionProfilingError(
                f"Column '{col_name}': non-finite Decimal value is not permitted."
            )
        # Return as-is — serialize_row_values → _serialize_scalar will convert to str
        return value

    # float — reject NaN and ±Inf
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            raise IngestionProfilingError(
                f"Column '{col_name}': NaN and infinite float values are not permitted."
            )
        return value

    # Reject nested dicts, lists, bytes, and other unsupported types
    if isinstance(value, (dict, list, bytes)):
        raise IngestionProfilingError(
            f"Column '{col_name}': value of type '{type(value).__name__}' "
            f"is not permitted in a dataset row."
        )

    # bool, int, str pass through as-is
    if isinstance(value, (bool, int, str)):
        return value

    raise IngestionProfilingError(
        f"Column '{col_name}': unsupported value type '{type(value).__name__}'."
    )


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class IngestionProfilingService:
    """Pure in-memory ingestion profiling service.

    Stateless — create a new instance per request or use the module-level
    profile_dataset() convenience function.
    """

    def profile_dataset(
        self,
        *,
        filename: str,
        content:  bytes,
    ) -> IngestionProfileResult:
        """Transform raw file bytes into a validated IngestionProfileResult.

        Parameters
        ----------
        filename:
            Original filename including extension (used for format detection).
        content:
            Raw file bytes.

        Returns
        -------
        IngestionProfileResult

        Raises
        ------
        IngestionProfilingError
            For any parse, serialization, or consistency failure.
            The original exception is always preserved as __cause__.
        """
        # ── Step 1: Parse ────────────────────────────────────────────────
        try:
            parsed = parse_ingestion_file(
                filename,
                content,
                max_file_bytes=settings.INGESTION_MAX_FILE_BYTES,
                max_rows=settings.INGESTION_MAX_ROWS,
                max_columns=settings.INGESTION_MAX_COLUMNS,
            )
        except Exception as exc:
            raise IngestionProfilingError(
                f"File parsing failed: {exc}"
            ) from exc

        original_headers: list[str] = parsed.original_column_names
        raw_rows:          list[list[Any]] = parsed.rows
        n_cols = len(original_headers)

        if n_cols == 0:
            raise IngestionProfilingError("Parsed dataset has no columns.")

        # ── Step 2: Normalize headers ────────────────────────────────────
        try:
            normalized_names: list[str] = normalize_column_names(original_headers)
        except Exception as exc:
            raise IngestionProfilingError(
                f"Column name normalization failed: {exc}"
            ) from exc

        # ── Step 3: Profile each column ──────────────────────────────────
        # Transpose: build per-column value lists
        col_values: list[list[Any]] = [[] for _ in range(n_cols)]
        for row in raw_rows:
            for ci, cell in enumerate(row):
                col_values[ci].append(cell)

        profiled_columns: list[ProfiledColumn] = []
        for ci in range(n_cols):
            col_vals = col_values[ci]
            original  = original_headers[ci]
            normalized = normalized_names[ci]

            try:
                inferred_type = infer_column_type_from_values(col_vals)
            except Exception as exc:
                raise IngestionProfilingError(
                    f"Type inference failed for column '{original}': {exc}"
                ) from exc

            missing_count = sum(1 for v in col_vals if is_missing_value(v))
            non_missing   = [v for v in col_vals if not is_missing_value(v)]
            unique_count  = len(set(str(v) for v in non_missing))
            nullable      = missing_count > 0

            # Collect up to _SAMPLE_LIMIT distinct non-missing samples
            seen_strs: set[str] = set()
            samples: list[Any] = []
            for v in non_missing:
                k = str(v)
                if k not in seen_strs:
                    seen_strs.add(k)
                    try:
                        s = serialize_sample_value(v)
                    except Exception:
                        s = None
                    if s is not None:
                        samples.append(s)
                if len(samples) >= _SAMPLE_LIMIT:
                    break

            profiled_columns.append(ProfiledColumn(
                ordinal_position=ci,
                original_name=original,
                normalized_name=normalized,
                inferred_type=inferred_type,
                nullable=nullable,
                missing_count=missing_count,
                unique_count=unique_count,
                sample_values=samples,
            ))

        # ── Step 4: Normalize rows ────────────────────────────────────────
        profiled_rows: list[ProfiledRow] = []
        for row_number, raw_row in enumerate(raw_rows):
            row_dict: dict[str, Any] = {}
            for ci, cell in enumerate(raw_row):
                norm_name = normalized_names[ci]
                orig_name = original_headers[ci]
                try:
                    converted = _convert_cell(orig_name, cell)
                except IngestionProfilingError:
                    raise
                except Exception as exc:
                    raise IngestionProfilingError(
                        f"Row {row_number}, column '{orig_name}': "
                        f"value conversion failed: {exc}"
                    ) from exc
                row_dict[norm_name] = converted

            # Serialize the completed row dict
            # This converts Decimal → str (preserving precision),
            # date/datetime → ISO str, and validates all values.
            try:
                row_dict = serialize_row_values(row_dict)
            except RowValuesError as exc:
                raise IngestionProfilingError(
                    f"Row {row_number} failed row-values validation: {exc}"
                ) from exc

            profiled_rows.append(ProfiledRow(
                row_number=row_number,
                values=row_dict,
            ))

        # ── Step 5: Consistency validation ───────────────────────────────
        result_row_count    = len(profiled_rows)
        result_column_count = len(profiled_columns)

        try:
            _validate_consistency(
                profiled_columns=profiled_columns,
                profiled_rows=profiled_rows,
                expected_normalized_names=normalized_names,
            )
        except IngestionProfilingError:
            raise
        except Exception as exc:
            raise IngestionProfilingError(
                f"Consistency validation failed: {exc}"
            ) from exc

        return IngestionProfileResult(
            original_filename=filename,
            detected_file_format=parsed.detected_file_format,
            worksheet_name=parsed.worksheet_name,
            row_count=result_row_count,
            column_count=result_column_count,
            columns=profiled_columns,
            rows=profiled_rows,
        )


# ---------------------------------------------------------------------------
# Infer type helper (thin delegation — avoids re-importing InferredColumnType
# into tests; centralizes the import)
# ---------------------------------------------------------------------------


def infer_column_type_from_values(values: list[Any]) -> InferredColumnType:
    """Thin wrapper around infer_column_type() from ingestion_parser."""
    from app.utils.ingestion_parser import infer_column_type
    return infer_column_type(values)


# ---------------------------------------------------------------------------
# Consistency validation
# ---------------------------------------------------------------------------


def _validate_consistency(
    profiled_columns: list[ProfiledColumn],
    profiled_rows:    list[ProfiledRow],
    expected_normalized_names: list[str],
) -> None:
    """Raise IngestionProfilingError if any consistency invariant is violated."""

    n_cols = len(profiled_columns)
    n_rows = len(profiled_rows)

    # Ordinal positions must be contiguous from 0
    ordinals = [c.ordinal_position for c in profiled_columns]
    if ordinals != list(range(n_cols)):
        raise IngestionProfilingError(
            f"Column ordinal positions are not contiguous from 0: {ordinals}"
        )

    # Normalized names must be unique
    norm_names = [c.normalized_name for c in profiled_columns]
    if len(set(norm_names)) != len(norm_names):
        raise IngestionProfilingError(
            f"Duplicate normalized column names detected: {norm_names}"
        )

    expected_keys = set(expected_normalized_names)

    # Row numbers must be contiguous from 0
    row_numbers = [r.row_number for r in profiled_rows]
    if row_numbers != list(range(n_rows)):
        raise IngestionProfilingError(
            f"Row numbers are not contiguous from 0: {row_numbers[:10]}…"
        )

    # Every row must contain exactly the set of normalized column names
    for row in profiled_rows:
        if set(row.values.keys()) != expected_keys:
            missing = expected_keys - set(row.values.keys())
            extra   = set(row.values.keys()) - expected_keys
            raise IngestionProfilingError(
                f"Row {row.row_number} has incorrect key set. "
                f"Missing: {missing}. Extra: {extra}."
            )


# ---------------------------------------------------------------------------
# Module-level convenience function
# ---------------------------------------------------------------------------

_service = IngestionProfilingService()


def profile_dataset(*, filename: str, content: bytes) -> IngestionProfileResult:
    """Module-level convenience wrapper around IngestionProfilingService."""
    return _service.profile_dataset(filename=filename, content=content)
