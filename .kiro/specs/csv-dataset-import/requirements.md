# Requirements: CSV Dataset Import Foundation

## Overview

Allow an authorised StatFlow operator to upload a structured CSV file, have it validated server-side against existing reference data, preview the parsed results with detailed diagnostics, and confirm a transactional bulk import of province-level indicator data points into PostgreSQL. No existing APIs or dashboard behaviour are changed.

---

## Glossary

| Term | Definition |
|---|---|
| **Natural key** | The combination (dataset_id, indicator_id, province_id, reference_year) that must be unique per DataPoint row |
| **Conflict** | A row whose natural key already exists in the database |
| **Duplicate** | A row whose natural key appears more than once within the uploaded file |
| **Preview token** | A short-lived server-side cache key returned by the preview endpoint and required by the confirm endpoint |
| **Operator** | A human user with write access to StatFlow; authentication is out of scope for this iteration |

---

## Requirements

### REQ-1: File Upload Constraints

- **REQ-1.1** Only CSV files (`.csv` extension, `text/csv` or `text/plain` MIME type) are accepted. Any other extension or MIME type returns HTTP 415.
- **REQ-1.2** The maximum accepted file size is 5 MB. Files exceeding this limit return HTTP 413.
- **REQ-1.3** Empty files (zero bytes) are rejected with HTTP 422 and a descriptive message.
- **REQ-1.4** Server-side filename sanitisation strips path separators, null bytes, and non-ASCII characters before any logging or error message. The original filename is never executed or stored permanently.
- **REQ-1.5** Uploaded file bytes are read into memory for parsing and discarded immediately after the response is returned. No file is written to disk.
- **REQ-1.6** The maximum number of data rows accepted per upload is 10,000. Files with more rows return HTTP 422.

---

### REQ-2: CSV Structure

- **REQ-2.1** The CSV must contain a header row as its first line. Missing header rows result in HTTP 422.
- **REQ-2.2** Required columns (case-insensitive, trimmed): `province_code`, `indicator_code`, `value`, `reference_year`, `dataset_name`. If any required column is absent the entire file is rejected with HTTP 422 and the list of missing column names.
- **REQ-2.3** Optional columns (ignored if absent): `source_name`, `source_url`. Extra unrecognised columns are silently ignored.
- **REQ-2.4** Rows with all empty cells are silently skipped and do not count toward the valid or invalid row totals.
- **REQ-2.5** The CSV is parsed using Python's standard `csv` module with `Sniffer`-detected delimiter fallback to comma. Tab-delimited and semicolon-delimited variants are supported transparently.
- **REQ-2.6** `dataset_name` must be a non-empty string in every row. A blank `dataset_name` cell is treated as a row-level validation error.
- **REQ-2.7** When `dataset_name` does not match an existing Dataset record, `source_name` must also be a non-empty string. A blank or absent `source_name` in this case is a row-level validation error. `source_url` is always optional.

---

### REQ-3: Row-Level Validation

Each non-empty data row is validated independently. All errors for a row are collected before moving to the next row.

- **REQ-3.1** `province_code` must match the `code` column of an existing `Province` record (case-insensitive). Unknown codes produce a validation error citing the row number and the unrecognised code.
- **REQ-3.2** `indicator_code` must match the `code` column of an existing `Indicator` record (case-insensitive). Unknown codes produce a validation error.
- **REQ-3.3** `value` must be parseable as a finite decimal number. Blank, non-numeric, infinite, or NaN values produce a validation error.
- **REQ-3.4** `reference_year` must be an integer in the range [1900, 2100] inclusive. Out-of-range or non-integer values produce a validation error.
- **REQ-3.5** Every validation error includes: row number (1-based, header = row 0), column name, raw cell value, and a human-readable description.

---

### REQ-4: Duplicate Detection

- **REQ-4.1** After row-level validation, the service identifies rows within the file whose resolved (indicator_id, province_id, reference_year) tuple appears more than once.
- **REQ-4.2** Duplicate rows are reported in the preview response. All but the first occurrence are flagged as duplicates.
- **REQ-4.3** A file containing duplicates can still be previewed but cannot be confirmed — the confirm endpoint returns HTTP 422 if the cached preview contains duplicates.

---

### REQ-5: Conflict Detection

- **REQ-5.1** After deduplication, the service queries the database for existing DataPoint rows whose (dataset_id, indicator_id, province_id, reference_year) matches any validated row.
- **REQ-5.2** Matching rows are classified as conflicts and reported in the preview response.
- **REQ-5.3** A file containing conflicts cannot be confirmed — the confirm endpoint returns HTTP 409 with the list of conflicting natural keys. Silent overwrite is explicitly forbidden.
- **REQ-5.4** The `dataset_name` column is required in every CSV (REQ-2.2). If a Dataset with that name exists, its `id` is used for conflict checking. If no matching Dataset exists, no pre-existing DataPoint can conflict (a new Dataset will be created on confirm), so conflict checking is skipped at preview time.

---

### REQ-6: Preview Response

The preview endpoint returns a structured JSON object:

- **REQ-6.1** `total_rows` — integer: count of non-empty data rows in the file.
- **REQ-6.2** `valid_rows` — integer: rows that passed all validation checks and are not duplicates.
- **REQ-6.3** `invalid_rows` — integer: rows that failed one or more validation checks.
- **REQ-6.4** `duplicate_rows` — integer: rows flagged as intra-file duplicates.
- **REQ-6.5** `conflict_rows` — integer: valid, non-duplicate rows whose natural key already exists in the database.
- **REQ-6.6** `errors` — array of row-level error objects. At most 100 error objects are returned regardless of how many errors exist in the file.
- **REQ-6.6a** `total_error_count` — integer: the true total number of row-level errors across all rows (may exceed 100).
- **REQ-6.6b** `errors_truncated` — boolean: `true` when `total_error_count > 100` (i.e. the `errors` array is a partial list).
- **REQ-6.7** `sample_records` — array of up to 10 parsed row objects from valid rows, for display in the frontend preview table.
- **REQ-6.8** `preview_token` — a UUID string. The client must supply this token to the confirm endpoint. The token expires after 15 minutes.
- **REQ-6.9** `can_confirm` — boolean: `true` only when `invalid_rows == 0 AND duplicate_rows == 0 AND conflict_rows == 0`.

---

### REQ-7: Confirm Import

- **REQ-7.1** The confirm endpoint accepts a `preview_token` and executes the import in a single database transaction.
- **REQ-7.2** If the token is unknown or expired the endpoint returns HTTP 404.
- **REQ-7.3** If the cached preview contains invalid, duplicate, or conflict rows the endpoint returns HTTP 422 (duplicates/invalid) or HTTP 409 (conflicts) and does not insert any records.
- **REQ-7.4** If a Dataset matching `dataset_name` does not exist, a new Dataset record is created within the same transaction before inserting DataPoints.
- **REQ-7.5** The `ImportService.confirm` method owns the transaction boundary explicitly using `async with session.begin():`. All operations within confirm — Dataset upsert and DataPoint bulk insert — execute inside this single context manager. If any operation raises an exception the context manager guarantees rollback before the exception propagates. Repository methods must not call `session.commit()` or `session.rollback()` directly.
- **REQ-7.6** On success the endpoint returns HTTP 201 with `imported_count` and the `dataset_id` of the target dataset.
- **REQ-7.7** After a successful confirm the preview token is invalidated and cannot be reused.

---

### REQ-8: Preview Token Lifecycle

- **REQ-8.1** Preview tokens are stored in an in-process Python dictionary (single-worker MVP). Redis is the documented upgrade path for multi-worker deployments but is not introduced in this iteration.
- **REQ-8.2** Token expiry is 15 minutes from creation.
- **REQ-8.3** A new preview of the same file creates a new token; prior tokens remain valid until they expire independently.
- **REQ-8.4** The token store holds the fully validated and deduplicated row set so the confirm endpoint does not re-parse the CSV.

---

### REQ-9: API Endpoints

- **REQ-9.1** `POST /api/v1/imports/csv/preview` — accepts `multipart/form-data` with field `file`. Returns the preview response defined in REQ-6.
- **REQ-9.2** `POST /api/v1/imports/csv/confirm` — accepts `application/json` body `{ "preview_token": "<uuid>" }`. Returns the import result defined in REQ-7.

---

### REQ-10: Frontend — Upload Page

- **REQ-10.1** A new route `/import` renders the CSV import page.
- **REQ-10.2** The page contains a drag-and-drop upload area that also accepts click-to-browse. Only `.csv` files are accepted by the file input (`accept=".csv"`).
- **REQ-10.3** Client-side checks before upload: file must have `.csv` extension, size must be ≤ 5 MB. Violations are shown inline without a network request.
- **REQ-10.4** During upload a progress indicator is displayed and the upload button is disabled.
- **REQ-10.5** On successful preview response the page transitions to a **Preview** state showing:
  - summary counts (total, valid, invalid, duplicate, conflict rows)
  - a validation error table (row, column, value, message) when `invalid_rows > 0`
  - when `errors_truncated` is `true`, a visible notice: "Showing the first 100 of {total_error_count} validation errors."
  - a sample records table (first 10 valid rows)
  - a "Confirm Import" button, enabled only when `can_confirm === true`
  - a "Upload a different file" action to reset the form
- **REQ-10.6** The "Confirm Import" button sends the `preview_token` to the confirm endpoint.
- **REQ-10.7** On successful confirm the page transitions to a **Success** state showing `imported_count` and a link back to the dashboard.
- **REQ-10.8** All error states (HTTP 4xx/5xx from either endpoint) display a user-readable message with the option to try again.
- **REQ-10.9** The import page is linked from the dashboard topbar or a visible navigation element.
- **REQ-10.10** The page is responsive: layout collapses to a single column on mobile (≤ 640 px).

---

### REQ-11: Security

- **REQ-11.1** Filenames are sanitised as per REQ-1.4 before any use.
- **REQ-11.2** CSV content is parsed with Python's `csv` module; no `eval`, `exec`, or shell invocation touches uploaded bytes.
- **REQ-11.3** All numeric and string fields are validated before database insertion; no raw CSV cell value is interpolated into SQL.
- **REQ-11.4** The preview token is a cryptographically random UUID; it does not encode any file content.
- **REQ-11.5** The confirm endpoint validates the token server-side; clients cannot bypass validation by crafting their own token payload.

---

### REQ-12: Testing

- **REQ-12.1** Backend: valid CSV produces correct preview counts and `can_confirm: true`.
- **REQ-12.2** Backend: malformed CSV (truncated, binary content) returns HTTP 422.
- **REQ-12.3** Backend: missing required columns return HTTP 422 with column names.
- **REQ-12.4** Backend: unknown `province_code` produces row-level error.
- **REQ-12.5** Backend: unknown `indicator_code` produces row-level error.
- **REQ-12.6** Backend: non-numeric `value` produces row-level error.
- **REQ-12.7** Backend: out-of-range `reference_year` produces row-level error.
- **REQ-12.8** Backend: intra-file duplicate rows are detected and reported.
- **REQ-12.9** Backend: database conflicts are detected and reported.
- **REQ-12.10** Backend: confirm with conflict token returns HTTP 409 and rolls back.
- **REQ-12.11** Backend: file exceeding 5 MB returns HTTP 413.
- **REQ-12.12** Frontend: client-side size validation shown before upload.
- **REQ-12.13** Frontend: preview summary counts displayed correctly.
- **REQ-12.14** Frontend: confirm button disabled when `can_confirm` is false.
- **REQ-12.16** Frontend: when `errors_truncated` is true, the truncation notice "Showing the first 100 of {N} validation errors." is displayed.

---

### REQ-13: Constraints

- **REQ-13.1** Excel (`.xlsx`, `.xls`) is not supported in this iteration.
- **REQ-13.2** No authentication or authorisation middleware is added in this iteration.
- **REQ-13.3** No background job queue (Celery, ARQ) is introduced.
- **REQ-13.4** Automatic overwrite or upsert of existing DataPoints is not supported. There is no `?force=true` or similar escape hatch; all conflicts hard-block confirmation with HTTP 409.
- **REQ-13.5** All existing API endpoints and dashboard behaviour are preserved unchanged.
- **REQ-13.6** District-level import is not supported in this iteration (province-level only).
- **REQ-13.7** The application runs in single-worker mode (`uvicorn … --workers 1`) for this MVP. The in-process token store is not safe for multi-worker deployments. This constraint must be documented in the deployment README. Redis-backed token storage is the designated upgrade path.
