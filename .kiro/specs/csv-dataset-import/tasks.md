# Implementation Plan: CSV Dataset Import Foundation

## Overview

Add a CSV upload, preview, and import workflow to StatFlow. Backend: two new FastAPI endpoints, a pure CSV parser/validator, an import service with a token store, and a bulk-insert repository. Frontend: a new `/import` page with drag-and-drop, preview summary, error table, sample table, and confirmation flow.

## Tasks

- [x] 1. Write `csv_parser.py` — pure parser and row validator
  - Create `backend/app/utils/csv_parser.py`
  - Define `ParsedRow`, `RowError`, `ParseResult` dataclasses
  - `ParsedRow.dataset_name` is `str` (non-optional — required column)
  - `ParsedRow.source_name` is `str | None` (required only when dataset_name is new)
  - Implement `parse_and_validate(raw_bytes, province_map, indicator_map, existing_dataset_names) → ParseResult`
  - Handle: header detection, delimiter sniffing (csv.Sniffer + comma fallback), blank row skip
  - Validate (all required): `province_code`, `indicator_code`, `value` (Decimal), `reference_year` ([1900,2100]), `dataset_name` (non-empty)
  - Validate conditionally: `source_name` non-empty when `dataset_name` not in `existing_dataset_names`
  - Collect all errors per row before moving to next row
  - Detect intra-file natural-key duplicates after all rows are parsed
  - Max rows guard: raise `RowLimitExceeded` if > 10,000 data rows
  - No database access — all lookup data passed in as arguments
  - References: REQ-2, REQ-3, REQ-4
  - Acceptance: unit tests in Task 7 pass against this function

- [x] 2. Write `import_repository.py`
  - Create `backend/app/repositories/import_repository.py`
  - Implement `load_province_map() → dict[str, UUID]` — SELECT id, code FROM provinces
  - Implement `load_indicator_map() → dict[str, UUID]` — SELECT id, code FROM indicators
  - Implement `load_dataset_names() → set[str]` — SELECT name FROM datasets
  - Implement `check_conflicts(dataset_id, rows) → list[NaturalKey]` — batch IN query
  - Implement `get_or_create_dataset(name, source_name, source_url) → Dataset`
    - Does NOT call `session.commit()` — caller owns transaction
  - Implement `bulk_insert_data_points(dataset_id, rows) → int`
    - Uses `session.add_all` + `await session.flush()` — does NOT commit
  - All methods: never call `session.commit()` or `session.rollback()` directly
  - Follow existing repository pattern: `__init__(self, session: AsyncSession)`
  - References: REQ-2.6, REQ-2.7, REQ-5.1, REQ-7.4, REQ-7.5
  - Acceptance: used successfully by ImportService in Task 3

- [x] 3. Write `import_service.py` — orchestration + token store
  - Create `backend/app/services/import_service.py`
  - Implement module-level `_TOKEN_STORE` dict with `_store_token`, `_retrieve_token`, `_invalidate_token` helpers
  - Token TTL: 15 minutes. Document single-worker limitation in module docstring (REQ-13.7)
  - Implement `ImportService.preview(raw_bytes: bytes) → CsvPreviewResponse`
    - Load `province_map`, `indicator_map`, `existing_dataset_names` from repository
    - Call `parse_and_validate(raw_bytes, province_map, indicator_map, existing_dataset_names)`
    - Call `check_conflicts` on valid, non-duplicate rows
    - Compute `can_confirm` flag
    - Build error list: `errors = all_errors[:100]`, `total_error_count = len(all_errors)`, `errors_truncated = total_error_count > 100`
    - Store validated payload in token store
    - Return `CsvPreviewResponse`
  - Implement `ImportService.confirm(preview_token: str) → CsvConfirmResponse`
    - Retrieve token; raise HTTP 404 if missing/expired
    - Raise HTTP 422 if `invalid_rows > 0` or `duplicate_rows > 0`
    - Raise HTTP 409 with conflict list if `conflict_rows > 0`
    - Use `async with self._session.begin():` — owns the transaction boundary
      - Call `get_or_create_dataset`
      - Call `bulk_insert_data_points`
    - Any exception inside the block rolls back automatically
    - Invalidate token on success
    - Return `CsvConfirmResponse`
  - References: REQ-6, REQ-7, REQ-8, REQ-13.7
  - Acceptance: integration tests in Task 8 pass

- [x] 4. Define Pydantic schemas (`schemas/imports.py`)
  - Create `backend/app/schemas/imports.py`
  - Define: `RowErrorSchema`, `SampleRecordSchema`, `CsvPreviewResponse`, `CsvConfirmRequest`, `CsvConfirmResponse`
  - `CsvPreviewResponse` includes `preview_token`, counts, `can_confirm`, `errors` (max 100 items), `total_error_count`, `errors_truncated`, `sample_records` (max 10)
  - `SampleRecordSchema` includes `dataset_name` field
  - `CsvConfirmResponse` includes `imported_count`, `dataset_id`
  - All models use `model_config = {"from_attributes": True}` where needed
  - References: REQ-6, REQ-6.6a, REQ-6.6b, REQ-7.6
  - Acceptance: schemas imported without error; used by endpoints in Task 5

- [x] 5. Implement import endpoints (`endpoints/imports.py`)
  - Create `backend/app/api/v1/endpoints/imports.py`
  - Implement `POST /imports/csv/preview`:
    - Accept `UploadFile` via `File(...)`
    - Guard: check MIME type (text/csv or text/plain) → HTTP 415
    - Guard: read `await file.read(MAX_SIZE + 1)` and check length → HTTP 413 if > 5 MB
    - Guard: empty bytes → HTTP 422
    - Sanitize filename (strip path separators, null bytes)
    - Delegate to `ImportService(db).preview(raw_bytes)`
    - Return `CsvPreviewResponse`
  - Implement `POST /imports/csv/confirm`:
    - Accept `CsvConfirmRequest` JSON body
    - Delegate to `ImportService(db).confirm(preview_token)`
    - Return `CsvConfirmResponse` with status 201
  - Update `backend/app/api/v1/api.py` to register `imports.router`
  - References: REQ-9, REQ-11
  - Acceptance: curl smoke tests return expected status codes

- [x] 6. Add frontend API helpers (`services/api.js`)
  - Add `importPreview(file: File) → Promise<CsvPreviewResponse>` to `frontend/src/services/api.js`
    - Uses `FormData` + `Content-Type: multipart/form-data`
  - Add `importConfirm(previewToken: string) → Promise<CsvConfirmResponse>`
    - Uses `application/json` body
  - Handle axios error responses: extract `response.data.detail` for display
  - References: REQ-9.1, REQ-9.2
  - Acceptance: called successfully from ImportPage in Task 9

- [x] 7. Write backend unit tests — pure CSV parser
  - Create `backend/tests/test_csv_parser.py`
  - Test: valid 3-row CSV (with dataset_name + source_name) → `valid_rows=3, errors=[], duplicate_indices=[]`
  - Test: missing required column (`dataset_name`) → `MissingColumnsError` raised
  - Test: blank `dataset_name` cell → row-level error on `dataset_name` column
  - Test: new dataset_name + blank `source_name` → row-level error on `source_name`
  - Test: existing dataset_name + blank `source_name` → valid (source_name not required)
  - Test: unknown province_code → error with row_number and raw_value
  - Test: unknown indicator_code → error
  - Test: non-numeric value (`"abc"`) → error
  - Test: `reference_year=1800` → error
  - Test: `reference_year=2101` → error
  - Test: two rows with same (indicator_code, province_code, reference_year) → `duplicate_indices` populated
  - Test: binary content passed as raw_bytes → `MalformedCsvError` raised
  - Test: 101 invalid rows → `len(errors) == 101` in raw ParseResult (truncation applied by service, not parser)
  - All tests call `parse_and_validate` directly with fixture dicts — no DB
  - References: REQ-2.2, REQ-2.6, REQ-2.7, REQ-3, REQ-4, REQ-12.1 – REQ-12.8
  - Acceptance: `pytest backend/tests/test_csv_parser.py` passes

- [x] 8. Write backend integration tests — endpoints
  - Create `backend/tests/test_imports.py`
  - Use `pytest-asyncio` + `httpx.AsyncClient` against the FastAPI app
  - Use a dedicated test database (seeded with at least 2 provinces and 2 indicators)
  - Test: valid CSV round-trip: preview → confirm → verify rows in DB
  - Test: file > 5 MB → HTTP 413
  - Test: `.txt` extension / wrong MIME → HTTP 415
  - Test: missing `value` column → HTTP 422 with column list in detail
  - Test: row with unknown province → HTTP 200, `invalid_rows=1`, `can_confirm=false`
  - Test: intra-file duplicate → `duplicate_rows=1`, `can_confirm=false`
  - Test: DB conflict → `conflict_rows=1`, `can_confirm=false`
  - Test: confirm with conflict token → HTTP 409
  - Test: confirm with expired token → HTTP 404
  - Test: transaction rollback — mock `bulk_insert` to raise `IntegrityError` mid-insert; assert 0 new rows in DB
  - Test: error truncation — upload CSV with 110 rows all with unknown province_code; assert `errors_truncated=true`, `len(errors)=100`, `total_error_count=110`
  - References: REQ-12.1 – REQ-12.11
  - Acceptance: `pytest backend/tests/test_imports.py` passes

- [x] 9. Build `ImportPage.jsx` and sub-components
  - Create `frontend/src/pages/ImportPage.jsx` — three-state machine (idle → previewing → success)
  - Create `frontend/src/components/import/DropZone.jsx`
    - Drag-and-drop + click-to-browse
    - `accept=".csv"`, client-side size check (≤ 5 MB)
    - Accessible: `role="region"`, `aria-label`, keyboard support
    - Shows filename and size after file is selected
  - Create `frontend/src/components/import/PreviewSummary.jsx`
    - Renders total/valid/invalid/duplicate/conflict count badges
    - Distinct accent colour per count type (token-driven)
  - Create `frontend/src/components/import/ValidationErrorTable.jsx`
    - Shows row, column, raw value, message
    - Only rendered when `invalid_rows > 0`
    - `overflow-x-auto` for mobile
  - Create `frontend/src/components/import/SampleRecordsTable.jsx`
    - Shows first 10 valid rows
    - Columns: row, province_code, indicator_code, value, reference_year
  - Wire confirm button: enabled only when `can_confirm === true`
  - Wire success state: shows `imported_count` + link to `/dashboard`
  - Wire all API error states with user-readable messages
  - Add `/import` link in `Topbar.jsx` (or as a nav item)
  - Update `frontend/src/app/router.jsx` to add `/import` route
  - References: REQ-10
  - Acceptance: page loads at /import; upload → preview → confirm flow works end-to-end with live backend

- [x] 10. Write frontend tests for ImportPage
  - Create `frontend/src/test/ImportPage.test.jsx`
  - Mock `../services/api` (`importPreview`, `importConfirm`)
  - Mock `../hooks/useZambiaGeoJSON` (prevent fetch warnings)
  - Test: file > 5 MB → error shown, no API call made
  - Test: `.txt` file selected → error shown, no API call made
  - Test: successful preview → summary counts rendered
  - Test: `can_confirm=false` → confirm button is disabled
  - Test: `can_confirm=true` → confirm button is enabled
  - Test: successful confirm → success state shows `imported_count`
  - Test: API returns 422 → error message displayed
  - Test: API returns 409 → conflict message displayed
  - Test: `errors_truncated=true` → notice "Showing the first 100 of {N} validation errors." is displayed
  - References: REQ-10.5, REQ-12.12 – REQ-12.16
  - Acceptance: `npx vitest run` passes all new tests alongside existing 47

- [x] 11. Final quality gates
  - Run `pytest backend/tests/` — all backend tests pass
  - Run `node node_modules/vitest/vitest.mjs run` — all frontend tests pass
  - Run `node node_modules/oxlint/dist/cli.js src` — exit 0
  - Smoke-test in browser: upload valid CSV → preview → confirm → see success count
  - Verify existing dashboard at `/dashboard` is unaffected
  - References: REQ-12, REQ-13.5
  - Acceptance: all automated checks pass; no regressions in existing tests

## Task Dependency Graph

```
1 (csv_parser) ──────────────────────────────────────────────► 7 (parser unit tests)
                                                                        │
2 (import_repository) ──► 3 (import_service) ──► 4 (schemas) ──► 5 (endpoints) ──► 8 (integration tests)
                                                                                              │
6 (api.js helpers) ──────────────────────────────────► 9 (ImportPage) ──► 10 (frontend tests)
                                                                                              │
                                                                              11 (quality gates)
```

Tasks 1 and 2 can start in parallel.  
Tasks 3, 4, 6, and 9 can start only after their respective predecessors.  
Tasks 7, 8, and 10 can run in parallel once their subjects are implemented.  
Task 11 must run last.

## Resolved Decisions

All five open questions from the initial spec have been answered:

| # | Question | Decision |
|---|---|---|
| N1 | `dataset_name` required? | **Yes** — required column in every CSV (REQ-2.2). Blank value is a row-level error. |
| N2 | Token store in multi-worker? | **Single-worker MVP** — in-process dict, documented deployment constraint (REQ-13.7). Redis path reserved for future iteration. |
| N3 | Force/overwrite option? | **No** — hard-block on any conflict; HTTP 409 with no bypass (REQ-13.4). |
| N4 | UI indication for truncated errors? | **Yes** — "Showing the first 100 of {N} validation errors." when `errors_truncated=true` (REQ-10.5, REQ-12.16). |
| N5 | `source_name` required for new datasets? | **Yes** — required when `dataset_name` does not match an existing Dataset (REQ-2.7). Optional otherwise. |

There are no remaining open questions.
