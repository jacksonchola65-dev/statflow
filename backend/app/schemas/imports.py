"""
schemas/imports.py
==================
Pydantic v2 request and response schemas for the CSV import workflow.

Endpoint contracts:
    POST /api/v1/imports/csv/preview  → CsvPreviewResponse
    POST /api/v1/imports/csv/confirm  → CsvConfirmResponse (body: CsvConfirmRequest)

All schemas are pure Pydantic models (not ORM-backed) except where noted.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from typing import Annotated, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Preview — error detail
# ---------------------------------------------------------------------------


class RowErrorSchema(BaseModel):
    """
    A single cell-level validation failure within a CSV data row.

    References: REQ-3.5
    """

    row_number: Annotated[int, Field(
        ge=1,
        description=(
            "1-based row number in the CSV file (header row = 0, "
            "first data row = 1)."
        ),
    )]
    column: Annotated[str, Field(
        min_length=1,
        description="Name of the CSV column that failed validation.",
    )]
    raw_value: Annotated[str, Field(
        description=(
            "Exact cell content after stripping surrounding whitespace. "
            "Empty string when the cell was blank."
        ),
    )]
    message: Annotated[str, Field(
        min_length=1,
        description="Human-readable description of the validation failure.",
    )]


# Alias kept for backward compatibility with the endpoint layer (Task 5)
CsvRowErrorSchema = RowErrorSchema


# ---------------------------------------------------------------------------
# Preview — conflict detail
# ---------------------------------------------------------------------------


class CsvConflictSchema(BaseModel):
    """
    Identifies a row that conflicts with an existing DataPoint in the database.

    The natural key is (dataset_id, indicator_id, province_id, reference_year)
    for province-level data points.  dataset_name is included so the operator
    knows which dataset the conflict belongs to without a separate lookup.
    """

    dataset_name: Annotated[str, Field(
        description=(
            "Name of the dataset as supplied in the CSV. "
            "Matches an existing Dataset record (case-insensitive)."
        ),
    )]
    indicator_id: Annotated[uuid.UUID, Field(
        description="UUID of the Indicator that conflicts.",
    )]
    province_id: Annotated[uuid.UUID, Field(
        description="UUID of the Province that conflicts.",
    )]
    reference_year: Annotated[int, Field(
        ge=1900, le=2100,
        description="Reference year of the conflicting DataPoint.",
    )]


# ---------------------------------------------------------------------------
# Preview — sample record
# ---------------------------------------------------------------------------


class SampleRecordSchema(BaseModel):
    """
    One row from the valid section of the uploaded CSV, shown in the
    frontend preview table (maximum 10 records returned).

    References: REQ-6.7
    """

    row_number: Annotated[int, Field(
        ge=1,
        description="1-based row number of this record in the source CSV.",
    )]
    province_code: Annotated[str, Field(
        min_length=1,
        description="Raw province code from the CSV (as uploaded).",
    )]
    indicator_code: Annotated[str, Field(
        min_length=1,
        description="Raw indicator code from the CSV (as uploaded).",
    )]
    value: Annotated[Decimal, Field(
        description="Parsed numeric value (Decimal for precision).",
    )]
    reference_year: Annotated[int, Field(
        ge=1900, le=2100,
        description="Reference year extracted from the CSV.",
    )]
    dataset_name: Annotated[str, Field(
        min_length=1,
        description="Dataset name as supplied in the CSV row.",
    )]


# ---------------------------------------------------------------------------
# Preview response
# ---------------------------------------------------------------------------


class CsvPreviewResponse(BaseModel):
    """
    Full response body for POST /api/v1/imports/csv/preview.

    The caller stores preview_token and passes it to the confirm endpoint.
    can_confirm == True iff the import may proceed without changes.

    References: REQ-6, REQ-6.6a, REQ-6.6b
    """

    preview_token: Annotated[str, Field(
        min_length=1,
        description=(
            "Opaque server-side token (URL-safe random string). "
            "Must be supplied to the confirm endpoint. "
            "Expires 15 minutes after preview."
        ),
    )]

    # Row counts — REQ-6.1 through REQ-6.5
    total_rows: Annotated[int, Field(
        ge=0,
        description=(
            "Total number of non-empty data rows found in the file "
            "(valid + invalid + duplicate)."
        ),
    )]
    valid_rows: Annotated[int, Field(
        ge=0,
        description=(
            "Rows that passed all validation checks and are not intra-file duplicates."
        ),
    )]
    invalid_rows: Annotated[int, Field(
        ge=0,
        description=(
            "Rows that failed one or more validation checks "
            "(including metadata-consistency errors)."
        ),
    )]
    duplicate_rows: Annotated[int, Field(
        ge=0,
        description=(
            "Rows whose natural key (dataset_name, indicator, province, year) "
            "appeared more than once in the file. "
            "Only second and subsequent occurrences are counted."
        ),
    )]
    conflict_rows: Annotated[int, Field(
        ge=0,
        description=(
            "Valid, non-duplicate rows whose natural key already exists "
            "in the database for the matching dataset."
        ),
    )]

    # Confirm gate — REQ-6.9
    can_confirm: Annotated[bool, Field(
        description=(
            "True only when invalid_rows == 0 AND duplicate_rows == 0 "
            "AND conflict_rows == 0.  When False the confirm endpoint "
            "will reject the token."
        ),
    )]

    # Error details (capped at 100) — REQ-6.6, REQ-6.6a, REQ-6.6b
    errors: Annotated[list[RowErrorSchema], Field(
        description=(
            "Row-level validation errors, capped at 100 items. "
            "Use total_error_count and errors_truncated for the full picture."
        ),
    )]
    total_error_count: Annotated[int, Field(
        ge=0,
        description="True total number of row-level errors (may exceed len(errors)).",
    )]
    errors_truncated: Annotated[bool, Field(
        description=(
            "True when total_error_count > 100, indicating the errors list "
            "is a partial view of all failures."
        ),
    )]

    # Preview data — REQ-6.7
    sample_records: Annotated[list[SampleRecordSchema], Field(
        description="Up to 10 valid rows for display in the preview table.",
    )]
    conflicts: Annotated[list[CsvConflictSchema], Field(
        description=(
            "Natural keys that conflict with existing DataPoints. "
            "Non-empty when conflict_rows > 0."
        ),
    )]


# ---------------------------------------------------------------------------
# Confirm request
# ---------------------------------------------------------------------------


class CsvConfirmRequest(BaseModel):
    """
    Request body for POST /api/v1/imports/csv/confirm.

    References: REQ-7.1
    """

    preview_token: Annotated[str, Field(
        min_length=1,
        description=(
            "The preview_token returned by the preview endpoint. "
            "Must be used within 15 minutes."
        ),
    )]


# ---------------------------------------------------------------------------
# Confirm response
# ---------------------------------------------------------------------------


class CsvConfirmResponse(BaseModel):
    """
    Response body for a successful POST /api/v1/imports/csv/confirm (HTTP 201).

    dataset_id is the primary (first) dataset UUID created or updated by this
    import.  dataset_ids contains all dataset UUIDs when the CSV spans multiple
    datasets.  datasets_created counts new Dataset records inserted.

    References: REQ-7.6
    """

    imported_count: Annotated[int, Field(
        ge=0,
        description="Number of DataPoint records inserted in this import.",
    )]
    datasets_created: Annotated[int, Field(
        ge=0,
        description=(
            "Number of new Dataset records created during this import. "
            "0 when all referenced datasets already existed."
        ),
    )]
    dataset_ids: Annotated[list[uuid.UUID], Field(
        description=(
            "UUIDs of every Dataset referenced by this import "
            "(both newly created and pre-existing)."
        ),
    )]

    @property
    def dataset_id(self) -> Optional[uuid.UUID]:
        """
        Convenience accessor returning the first (primary) dataset UUID,
        or None when dataset_ids is empty.

        Satisfies REQ-7.6: 'dataset_id of the target dataset'.
        For multi-dataset imports use dataset_ids directly.
        """
        return self.dataset_ids[0] if self.dataset_ids else None
