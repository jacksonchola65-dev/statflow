"""
import_service.py
=================
Orchestration layer for the CSV import pipeline.

Responsibilities
----------------
1. Preview   — parse + validate + conflict-detect + store token
2. Confirm   — verify token + recheck conflicts + transact + return counts

Single-worker limitation (REQ-13.7)
------------------------------------
⚠ WARNING: The token store is an in-process Python dict. It is NOT safe
for multi-worker deployments (``uvicorn --workers N`` where N > 1).
Each worker has its own memory space; a confirm request landing on a
different worker than the preview request will return HTTP 404 (token not
found). For this MVP the application MUST run with a single worker:

    uvicorn app.main:app --workers 1

Redis is the designated upgrade path. To migrate, replace the three
helper functions _store_token / _retrieve_token / _invalidate_token
with a Redis-backed implementation. ImportService itself needs no changes.

Deployment note: document ``--workers 1`` in the deployment README before
exposing this service in any environment that runs more than one process.

Transaction ownership
---------------------
ImportService.confirm() owns the transaction boundary:

    async with self._session.begin():
        ...

Repository methods must never call session.commit() or session.rollback().
If any operation inside the block raises an exception the context manager
rolls back automatically before the exception propagates to the endpoint.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any

from app.repositories.import_repository import ConflictKey, DatasetResolution, ImportRepository
from app.utils.csv_parser import (
    ParsedRow,
    RowError,
    parse_and_validate,
)
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

TOKEN_TTL = timedelta(minutes=15)
MAX_ERROR_RESPONSE = 100  # errors returned to caller; parser collects all
MAX_SAMPLE_RECORDS = 10  # sample records in preview response

# ---------------------------------------------------------------------------
# Token store — module-level in-process dict (single-worker MVP)
# ---------------------------------------------------------------------------


@dataclass
class _TokenEntry:
    """One entry in the in-process token store."""

    payload: "CachedPreview"
    # created_at is stored so expiry can be checked as: now(UTC) > created_at + TOKEN_TTL
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


_TOKEN_STORE: dict[str, _TokenEntry] = {}


def _store_token(payload: "CachedPreview") -> str:
    """
    Store a preview payload and return a UUID4 token string (REQ-11.4).

    The token is a random UUID (128 bits of entropy, cryptographically random
    on CPython). It does not encode any file content.
    """
    token = str(uuid.uuid4())
    _TOKEN_STORE[token] = _TokenEntry(payload=payload)
    return token


def _retrieve_token(token: str) -> "CachedPreview | None":
    """
    Look up a token. Returns the payload or None if the token is missing
    or has expired. Expired entries are removed on access (lazy eviction).

    Expiry: datetime.utcnow() > created_at + TOKEN_TTL (15 minutes).
    """
    entry = _TOKEN_STORE.get(token)
    if entry is None:
        return None
    if datetime.now(timezone.utc) > entry.created_at + TOKEN_TTL:
        _TOKEN_STORE.pop(token, None)
        return None
    return entry.payload


def _invalidate_token(token: str) -> None:
    """Remove a token from the store. Safe to call if the token is absent."""
    _TOKEN_STORE.pop(token, None)


# ---------------------------------------------------------------------------
# Internal data transfer objects
# ---------------------------------------------------------------------------


@dataclass
class SampleRecord:
    """One row of data shown in the preview table."""

    row_number: int
    province_code: str
    indicator_code: str
    value: Any  # Decimal — kept as-is; serialised by endpoint layer
    reference_year: int
    dataset_name: str


@dataclass
class MetadataError:
    """A dataset-metadata consistency error reported as a RowError."""

    row_number: int
    column: str
    raw_value: str
    message: str


@dataclass
class CachedPreview:
    """
    Everything stored in the token store.

    The confirm step reads this directly; it does NOT re-parse the CSV.
    """

    valid_rows: list[ParsedRow]
    all_errors: list[RowError]  # ALL row errors (not capped)
    duplicate_row_numbers: list[int]
    conflict_keys: list[ConflictKey]
    metadata_errors: list[RowError]  # metadata consistency errors
    total_rows: int


@dataclass
class PreviewData:
    """
    Returned by ImportService.preview().
    The endpoint layer converts this to the Pydantic response schema.
    """

    preview_token: str
    total_rows: int
    valid_rows: int
    invalid_rows: int
    duplicate_rows: int
    conflict_rows: int
    can_confirm: bool
    errors: list[RowError]  # capped at MAX_ERROR_RESPONSE
    total_error_count: int
    errors_truncated: bool
    sample_records: list[SampleRecord]
    conflicts: list[ConflictKey]


@dataclass
class ConfirmResult:
    """
    Returned by ImportService.confirm().
    The endpoint layer converts this to the Pydantic response schema.
    """

    imported_count: int
    datasets_created: int
    dataset_ids: list[uuid.UUID]


# ---------------------------------------------------------------------------
# Metadata consistency checker
# ---------------------------------------------------------------------------


def _check_metadata_consistency(
    valid_rows: list[ParsedRow],
) -> list[RowError]:
    """
    Verify that all rows for the same (normalised) dataset_name agree on
    source_name and source_url.

    Rules
    -----
    - Group rows by dataset_name.strip().lower()
    - Within each group the FIRST row establishes the canonical values.
    - Every subsequent row is compared to the first row's values:
        source_name : compared case-insensitively after strip
        source_url  : compared exactly after strip (URLs are case-sensitive)
    - A conflict produces a RowError pointing at the offending row.
    - The first row is never reported as an error (it sets the baseline).

    Returns a list of RowError; empty list means all rows are consistent.
    """
    # canonical_meta[normalised_name] = (source_name_lower_stripped, source_url_stripped, row_number)
    canonical_meta: dict[str, tuple[str | None, str | None, int]] = {}
    errors: list[RowError] = []

    for row in valid_rows:
        key = row.dataset_name.strip().lower()
        row_source_name = (row.source_name or "").strip()
        row_source_url = (row.source_url or "").strip() or None

        if key not in canonical_meta:
            canonical_meta[key] = (
                row_source_name.lower() if row_source_name else None,
                row_source_url,
                row.row_number,
            )
            continue

        canon_sname_lower, canon_url, first_row_num = canonical_meta[key]

        # Compare source_name (case-insensitive)
        this_sname_lower = row_source_name.lower() if row_source_name else None
        if this_sname_lower != canon_sname_lower:
            errors.append(
                RowError(
                    row_number=row.row_number,
                    column="source_name",
                    raw_value=row.source_name or "",
                    message=(
                        f"source_name '{row.source_name}' is inconsistent with "
                        f"the value set by row {first_row_num} for dataset "
                        f"'{row.dataset_name}'. All rows for the same dataset must "
                        "use the same source_name."
                    ),
                )
            )

        # Compare source_url (exact after strip)
        if row_source_url != canon_url:
            errors.append(
                RowError(
                    row_number=row.row_number,
                    column="source_url",
                    raw_value=row.source_url or "",
                    message=(
                        f"source_url '{row.source_url}' is inconsistent with "
                        f"the value set by row {first_row_num} for dataset "
                        f"'{row.dataset_name}'. All rows for the same dataset must "
                        "use the same source_url."
                    ),
                )
            )

    return errors


# ---------------------------------------------------------------------------
# ImportService
# ---------------------------------------------------------------------------


class ImportService:
    """
    Orchestrates the CSV import workflow: preview and confirm.

    Both methods depend on an AsyncSession passed at construction time.
    The session is NOT committed or rolled back by this class except via
    the explicit ``async with self._session.begin()`` in confirm().
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._repo = ImportRepository(session)

    # ------------------------------------------------------------------
    # Preview
    # ------------------------------------------------------------------

    async def preview(self, raw_bytes: bytes) -> PreviewData:
        """
        Parse, validate, and conflict-check a CSV file.

        Steps
        -----
        1. Load province_map, indicator_map, existing_dataset_names from DB.
        2. Call parse_and_validate — pure function, no I/O.
        3. Check metadata consistency across valid rows.
        4. Collect all errors (row errors + metadata errors).
        5. For each existing dataset referenced by valid non-duplicate rows,
           run a DB conflict check.
        6. Store a CachedPreview in the token store.
        7. Build and return PreviewData.

        Parser exceptions (EmptyFileError, MalformedCsvError,
        MissingColumnsError, RowLimitExceeded) are allowed to propagate;
        the endpoint layer maps them to HTTP status codes.
        """
        # Step 1: load reference data
        province_map = await self._repo.load_province_map()
        indicator_map = await self._repo.load_indicator_map()
        dataset_names = await self._repo.load_dataset_names()

        # Step 2: parse + row-level validate (pure, no I/O)
        parse_result = parse_and_validate(raw_bytes, province_map, indicator_map, dataset_names)

        # Step 3: metadata consistency check across valid rows
        metadata_errors = _check_metadata_consistency(parse_result.valid_rows)

        # Step 4: aggregate all errors
        all_errors: list[RowError] = list(parse_result.errors) + metadata_errors

        # Step 5: conflict detection per dataset
        # Only check rows that are valid AND non-duplicate AND not already
        # flagged by metadata errors for their dataset.
        #
        # We group valid rows by normalised dataset_name. For each group:
        #   - If the dataset already exists → run conflict check against it.
        #   - If the dataset is new        → no DB conflicts possible.
        conflict_keys: list[ConflictKey] = []

        valid_non_dup = parse_result.valid_rows  # duplicates stay in duplicate_row_numbers

        # Build per-dataset groups
        dataset_groups: dict[str, list[ParsedRow]] = {}
        for row in valid_non_dup:
            norm = row.dataset_name.strip().lower()
            dataset_groups.setdefault(norm, []).append(row)

        for norm_name, rows in dataset_groups.items():
            existing = await self._repo.find_dataset_by_name(norm_name)
            if existing is None:
                # New dataset — no pre-existing DataPoints to conflict with
                continue
            raw_conflicts = await self._repo.check_conflicts(existing.id, rows)
            # Enrich with dataset_name (from the CSV rows) for the response
            first_row_name = rows[0].dataset_name if rows else ""
            for ck in raw_conflicts:
                conflict_keys.append(
                    ConflictKey(
                        dataset_id=ck.dataset_id,
                        indicator_id=ck.indicator_id,
                        province_id=ck.province_id,
                        reference_year=ck.reference_year,
                        dataset_name=first_row_name,
                    )
                )

        # Step 6: store token
        cached = CachedPreview(
            valid_rows=parse_result.valid_rows,
            all_errors=all_errors,
            duplicate_row_numbers=parse_result.duplicate_row_numbers,
            conflict_keys=conflict_keys,
            metadata_errors=metadata_errors,
            total_rows=len(parse_result.valid_rows)
            + len(all_errors)
            + len(parse_result.duplicate_row_numbers),
        )

        # Add metadata error rows to invalid count
        # (metadata errors apply to rows that were otherwise valid)
        # Re-count properly:
        meta_error_row_numbers = {e.row_number for e in metadata_errors}
        valid_rows_clean = [
            r for r in parse_result.valid_rows if r.row_number not in meta_error_row_numbers
        ]

        invalid_rows = len(parse_result.errors) + len(meta_error_row_numbers)
        duplicate_rows = len(parse_result.duplicate_row_numbers)
        conflict_rows = len(conflict_keys)
        valid_rows_count = len(valid_rows_clean)

        # Recompute total_rows as the sum of all categories
        total_rows_computed = valid_rows_count + invalid_rows + duplicate_rows

        can_confirm = invalid_rows == 0 and duplicate_rows == 0 and conflict_rows == 0

        total_error_count = len(all_errors)
        errors_capped = all_errors[:MAX_ERROR_RESPONSE]
        errors_truncated = total_error_count > MAX_ERROR_RESPONSE

        sample_records = [
            SampleRecord(
                row_number=r.row_number,
                province_code=r.province_code,
                indicator_code=r.indicator_code,
                value=r.value,
                reference_year=r.reference_year,
                dataset_name=r.dataset_name,
            )
            for r in valid_rows_clean[:MAX_SAMPLE_RECORDS]
        ]

        # Store before building response so token is available
        cached.valid_rows = valid_rows_clean  # store only clean valid rows
        token = _store_token(cached)

        return PreviewData(
            preview_token=token,
            total_rows=total_rows_computed,
            valid_rows=valid_rows_count,
            invalid_rows=invalid_rows,
            duplicate_rows=duplicate_rows,
            conflict_rows=conflict_rows,
            can_confirm=can_confirm,
            errors=errors_capped,
            total_error_count=total_error_count,
            errors_truncated=errors_truncated,
            sample_records=sample_records,
            conflicts=conflict_keys,
        )

    # ------------------------------------------------------------------
    # Confirm
    # ------------------------------------------------------------------

    async def confirm(self, preview_token: str) -> ConfirmResult:
        """
        Execute the import transactionally.

        Steps
        -----
        1. Retrieve token; raise HTTP 404 if missing or expired.
        2. Block if preview has errors, duplicates, conflicts, or metadata errors.
        3. Open ``async with self._session.begin():``.
        4. Inside the transaction:
           a. Recheck DB conflicts (race-condition guard).
           b. For each distinct dataset in valid_rows:
              - get_or_create via repository (preserves canonical name).
           c. Bulk insert all DataPoints.
        5. Invalidate token (only after the transaction block exits cleanly).
        6. Return ConfirmResult.

        The token is NOT invalidated if the transaction fails, so a client
        can retry with the same token if the failure was transient.
        """
        # Step 1: retrieve
        cached = _retrieve_token(preview_token)
        if cached is None:
            raise HTTPException(
                status_code=404,
                detail="Preview token not found or expired.",
            )

        # Step 2: gate
        if cached.all_errors:
            raise HTTPException(
                status_code=422,
                detail=(
                    f"Preview contains {len(cached.all_errors)} validation "
                    "error(s). Fix all errors before confirming."
                ),
            )
        if cached.duplicate_row_numbers:
            raise HTTPException(
                status_code=422,
                detail=(
                    f"Preview contains {len(cached.duplicate_row_numbers)} "
                    "duplicate row(s). Remove duplicates before confirming."
                ),
            )
        if cached.conflict_keys:
            raise HTTPException(
                status_code=409,
                detail={
                    "message": (
                        f"{len(cached.conflict_keys)} row(s) conflict with "
                        "existing data. Import aborted."
                    ),
                    "conflicts": [
                        {
                            "dataset_id": str(ck.dataset_id),
                            "indicator_id": str(ck.indicator_id),
                            "province_id": str(ck.province_id),
                            "reference_year": ck.reference_year,
                        }
                        for ck in cached.conflict_keys
                    ],
                },
            )

        # Step 3 + 4: transact
        # The token is NOT invalidated yet — if the transaction fails the
        # token remains valid so the caller can retry.
        #
        # Transaction strategy: use begin_nested() (SAVEPOINT) when the
        # session already has an active transaction (as is the case when
        # the session comes from the get_db FastAPI dependency, which
        # manages the outer transaction).  If no transaction is active,
        # begin() starts one.  Either way, all work commits or rolls back
        # atomically.
        imported_count = 0
        datasets_created = 0
        dataset_ids: list[uuid.UUID] = []

        # Determine whether an outer transaction is already in progress.
        # SQLAlchemy async sessions start a transaction lazily on first use,
        # so we check via the sync driver's in_transaction() flag.
        in_outer_txn = self._session.in_transaction()
        txn_cm = self._session.begin_nested() if in_outer_txn else self._session.begin()

        async with txn_cm:
            # 4a: recheck conflicts (race-condition guard)
            dataset_groups: dict[str, list[ParsedRow]] = {}
            for row in cached.valid_rows:
                norm = row.dataset_name.strip().lower()
                dataset_groups.setdefault(norm, []).append(row)

            for norm_name, rows in dataset_groups.items():
                existing = await self._repo.find_dataset_by_name(norm_name)
                if existing is not None:
                    fresh_conflicts = await self._repo.check_conflicts(existing.id, rows)
                    if fresh_conflicts:
                        # Abort with 409; transaction rolls back automatically
                        raise HTTPException(
                            status_code=409,
                            detail={
                                "message": (
                                    "A conflict was detected between preview and "
                                    "confirmation. Import aborted. Run a new "
                                    "preview to see updated conflicts."
                                ),
                                "conflicts": [
                                    {
                                        "dataset_id": str(ck.dataset_id),
                                        "indicator_id": str(ck.indicator_id),
                                        "province_id": str(ck.province_id),
                                        "reference_year": ck.reference_year,
                                    }
                                    for ck in fresh_conflicts
                                ],
                            },
                        )

            # 4b: resolve datasets; 4c: bulk insert per dataset
            # Use the first row of each group for metadata (consistency was
            # verified at preview time — metadata errors block confirm).
            for norm_name, rows in dataset_groups.items():
                first = rows[0]

                resolution: DatasetResolution = await self._repo.create_dataset_if_absent(
                    dataset_name=first.dataset_name,
                    source_name=first.source_name,
                    source_url=first.source_url,
                )

                dataset_ids.append(resolution.dataset.id)
                if resolution.created:
                    datasets_created += 1

                count = await self._repo.bulk_insert_data_points(
                    dataset_id=resolution.dataset.id,
                    rows=rows,
                )
                imported_count += count

        # Step 5: invalidate token only after successful transaction exit
        _invalidate_token(preview_token)

        return ConfirmResult(
            imported_count=imported_count,
            datasets_created=datasets_created,
            dataset_ids=dataset_ids,
        )
