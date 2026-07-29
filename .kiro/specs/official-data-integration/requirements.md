# Requirements Document: Official Data Integration

## Introduction

The **Official Data Integration** feature builds the full ingestion, catalogue management, and intelligence pipeline that powers StatFlow's statistical data platform. It is structured as five milestones, sequenced so that the foundational backend work is complete and testable before any frontend UI is built.

**Milestone 1 — Ingestion Foundation** (this spec's first executable milestone) establishes the file parsing, column profiling, and ingestion metadata infrastructure. It deliberately stores no full dataset rows — only ingestion job metadata and per-column profiles. This foundation is format-agnostic and designed to serve both official government datasets and future private organisational uploads.

**Milestone 2 — Row Persistence** adds approved ingestion storage, versioning, and dataset querying on top of the Milestone 1 job infrastructure.

**Milestone 3 — Official Dataset Importers** adds scheduled and manual importers for specific Zambian and international data publishers.

**Milestone 4 — Registry Management UI** adds the frontend pages for data source and dataset registry management (previously the entire scope of the old spec — retained and moved here).

**Milestone 5 — Organisational Data Intelligence** adds private uploads, access isolation, automatic profiling, AI-generated insights, and comparison with official datasets.

---

## Glossary

| Term | Definition |
|---|---|
| **IngestionJob** | A single file-inspection run. Created when `POST /ingestion/inspect` is called. Records outcome and links to column metadata. |
| **DatasetColumn** | Per-column metadata produced during an ingestion job: original name, normalised name, inferred type, nullable flag, missing count, unique count, sample values. |
| **IngestionStatus** | Enum tracking the lifecycle of an IngestionJob: `PENDING`, `RUNNING`, `COMPLETED`, `FAILED`. |
| **InferredColumnType** | Enum of detected data types: `INTEGER`, `FLOAT`, `DATE`, `DATETIME`, `BOOLEAN`, `TEXT`, `UNKNOWN`. |
| **Column normalisation** | Deterministic transformation of a raw column header to a stable identifier: lower-cased, whitespace collapsed to underscores, non-alphanumeric characters stripped, leading digits prefixed with `col_`. |
| **Column profiling** | Counting non-null, null, and unique values and collecting up to 5 sample values per column. |
| **DataSource** | Existing model — a publishing organisation (e.g. Zambia Statistics Agency). |
| **DatasetRegistry** | Existing model — a catalogued dataset published by a DataSource. |
| **CSRF** | Cross-Site Request Forgery protection; all mutating endpoints require `X-CSRF-Token`. |
| **ADMIN / DATA_MANAGER** | Roles already implemented in auth-foundation that may call the ingestion endpoint. |

---

## Milestone 1 — Ingestion Foundation

### REQ-M1-1: IngestionJob Model

**User Story:** As a system tracking file inspection history, I need an `IngestionJob` record that captures the full lifecycle of every file inspection, so that I can audit what was inspected, when, and with what outcome.

#### Acceptance Criteria

1. THE `ingestion_jobs` table SHALL contain the following columns: `id` (UUID PK), `dataset_registry_id` (UUID FK → `dataset_registry.id` RESTRICT, nullable), `status` (IngestionStatus enum, not null), `original_filename` (string, not null), `stored_filename` (string, nullable — reserved for future storage), `file_format` (FileFormat enum, not null), `file_size_bytes` (integer, not null), `row_count` (integer, nullable — null until parsing completes), `column_count` (integer, nullable — null until parsing completes), `started_at` (datetime with tz, nullable), `completed_at` (datetime with tz, nullable), `failed_at` (datetime with tz, nullable), `error_message` (text, nullable), `created_by_user_id` (UUID FK → `users.id` SET NULL, nullable), `created_at` (datetime with tz, not null, server default now()), `updated_at` (datetime with tz, not null, server default now(), auto-updated on change).
2. THE `status` column SHALL use a PostgreSQL native enum named `ingestion_status_enum`.
3. THE `file_format` column SHALL use the existing `file_format_enum` PostgreSQL enum (CSV, XLSX, JSON, API, OTHER) already defined in the `data_source.py` model.
4. THE `IngestionJob` ORM model SHALL use SQLAlchemy `mapped_column` / `Mapped` annotations consistent with the existing model conventions in this codebase.
5. THE `updated_at` column SHALL be automatically refreshed on every ORM-level update via an `onupdate` lambda.

---

### REQ-M1-2: DatasetColumn Model

**User Story:** As a data analyst reviewing an inspection result, I need per-column metadata stored for every column found in the uploaded file, so that I can understand the structure and quality of the dataset without downloading the file.

#### Acceptance Criteria

1. THE `dataset_columns` table SHALL contain the following columns: `id` (UUID PK), `ingestion_job_id` (UUID FK → `ingestion_jobs.id` CASCADE, not null, indexed), `original_name` (string, not null — the raw header as it appears in the file), `normalized_name` (string, not null — deterministic normalised form), `inferred_type` (InferredColumnType enum, not null), `nullable` (boolean, not null — true if any missing values were detected), `missing_count` (integer, not null, default 0), `unique_count` (integer, not null, default 0), `sample_values` (JSON array of up to 5 string representations, nullable), `created_at` (datetime with tz, not null, server default now()).
2. THE `inferred_type` column SHALL use a PostgreSQL native enum named `inferred_column_type_enum`.
3. THE relationship from `IngestionJob` to `DatasetColumn` SHALL be `one-to-many` with `cascade="all, delete-orphan"`.

---

### REQ-M1-3: Ingestion Status Enum

**User Story:** As a developer consuming ingestion job records, I need a well-defined status lifecycle enum, so that I can reliably interpret the state of any job.

#### Acceptance Criteria

1. THE `IngestionStatus` enum SHALL define exactly four values: `PENDING`, `RUNNING`, `COMPLETED`, `FAILED`.
2. `PENDING` SHALL be the initial status when a job record is created.
3. `RUNNING` SHALL be set when file parsing begins.
4. `COMPLETED` SHALL be set when parsing and profiling finish without error.
5. `FAILED` SHALL be set when any unrecoverable error occurs during inspection; `error_message` SHALL be populated at the same time.

---

### REQ-M1-4: Inferred Column Type Enum

**User Story:** As a data analyst, I need a consistent set of inferred column types so that I can understand what kind of data each column contains.

#### Acceptance Criteria

1. THE `InferredColumnType` enum SHALL define exactly seven values: `INTEGER`, `FLOAT`, `DATE`, `DATETIME`, `BOOLEAN`, `TEXT`, `UNKNOWN`.
2. `UNKNOWN` SHALL be used when the type inference algorithm cannot determine a type with confidence.
3. Type inference SHALL be applied column-by-column, independently.

---

### REQ-M1-5: Supported File Formats

**User Story:** As a DATA_MANAGER uploading a statistical dataset, I need the system to accept CSV and XLSX files, so that I can work with the two most common formats for government statistical data.

#### Acceptance Criteria

1. THE ingestion engine SHALL support exactly two file formats in Milestone 1: **CSV** and **XLSX**.
2. For XLSX files, THE ingestion engine SHALL inspect **only the first worksheet**. Additional worksheets SHALL be ignored without error.
3. THE system SHALL detect the file format from the `Content-Type` header and the file extension. If the two disagree, the `Content-Type` header SHALL take precedence.
4. IF the uploaded file format is not CSV or XLSX, THE system SHALL return HTTP 415 Unsupported Media Type.

---

### REQ-M1-6: File-Size Limit

**User Story:** As an operator protecting the platform from resource exhaustion, I want a configurable maximum file size, so that oversized uploads are rejected before parsing begins.

#### Acceptance Criteria

1. THE ingestion engine SHALL reject files whose byte count exceeds a configurable `INGESTION_MAX_FILE_BYTES` setting.
2. `INGESTION_MAX_FILE_BYTES` SHALL default to **10 MB** (10 × 1024 × 1024 bytes).
3. `INGESTION_MAX_FILE_BYTES` SHALL be readable from the environment variable of the same name.
4. IF the file exceeds the limit, THE system SHALL return HTTP 413 with a message stating the limit and the actual size.
5. THE size check SHALL occur **before** any parsing begins, using the raw byte length of the upload.

---

### REQ-M1-7: Configurable Row-Count Limit

**User Story:** As an operator, I want a configurable maximum number of rows to prevent extremely long-running inspection jobs.

#### Acceptance Criteria

1. THE ingestion engine SHALL reject files whose row count (excluding the header row) exceeds a configurable `INGESTION_MAX_ROWS` setting.
2. `INGESTION_MAX_ROWS` SHALL default to **100,000**.
3. `INGESTION_MAX_ROWS` SHALL be readable from the environment variable of the same name.
4. IF the row count exceeds the limit, THE system SHALL return HTTP 422 with a message identifying the limit and the actual row count.
5. The row count check SHALL occur after the header row is read but before full column profiling completes.

---

### REQ-M1-8: Configurable Column-Count Limit

**User Story:** As an operator, I want a configurable maximum number of columns to prevent pathological wide-file attacks.

#### Acceptance Criteria

1. THE ingestion engine SHALL reject files whose column count exceeds a configurable `INGESTION_MAX_COLUMNS` setting.
2. `INGESTION_MAX_COLUMNS` SHALL default to **500**.
3. `INGESTION_MAX_COLUMNS` SHALL be readable from the environment variable of the same name.
4. IF the column count exceeds the limit, THE system SHALL return HTTP 422 with a message identifying the limit and the actual count.
5. The column count check SHALL occur immediately after the header row is parsed.

---

### REQ-M1-9: Deterministic Column-Name Normalisation

**User Story:** As a developer building downstream features on top of ingestion results, I need column names to be normalised to stable identifiers, so that I can reference columns programmatically regardless of how they appear in the original file.

#### Acceptance Criteria

1. THE normalisation algorithm SHALL apply the following transformations in order:
   a. Strip leading and trailing whitespace.
   b. Convert all characters to lower case.
   c. Replace any run of whitespace characters (space, tab, newline) with a single underscore.
   d. Strip any character that is not a letter, digit, or underscore.
   e. If the result begins with a digit, prepend `col_`.
   f. If the result is empty after all transformations, use `col_<position>` where `<position>` is the 1-based column index.
2. THE normalisation function SHALL be a pure function with no side effects, independently importable and testable.
3. THE `normalized_name` stored in `DatasetColumn` SHALL be the output of this function applied to `original_name`.

---

### REQ-M1-10: Duplicate Normalised-Name Handling

**User Story:** As a user uploading a file with headers that normalise to the same identifier, I want a clear, deterministic resolution so that every column gets a unique normalised name.

#### Acceptance Criteria

1. IF two or more columns normalise to the same string, THE system SHALL append `_2`, `_3`, … (incrementing integers) to the second and subsequent duplicates, in left-to-right column order.
2. The deduplication counter SHALL be applied only when a collision is detected; unique names are not modified.
3. THE system SHALL NOT return an error for duplicate normalised names — it SHALL silently deduplicate and continue.

---

### REQ-M1-11: Deterministic Type Inference

**User Story:** As a data analyst, I need the system to infer each column's data type from its values, so that I can understand the dataset structure without opening the file.

#### Acceptance Criteria

1. THE type inference algorithm SHALL evaluate every non-null value in a column and return the most specific type that fits all of them.
2. Type precedence (most specific to least): `BOOLEAN` → `INTEGER` → `FLOAT` → `DATE` → `DATETIME` → `TEXT`.
3. `BOOLEAN` SHALL be inferred when all non-null values are in the set `{"true", "false", "yes", "no", "1", "0"}` (case-insensitive).
4. `INTEGER` SHALL be inferred when all non-null values parse as Python `int` without decimal points.
5. `FLOAT` SHALL be inferred when all non-null values parse as Python `float`, including those parseable as `int`.
6. `DATE` SHALL be inferred when all non-null values parse as ISO 8601 date strings (YYYY-MM-DD).
7. `DATETIME` SHALL be inferred when all non-null values parse as ISO 8601 datetime strings.
8. `TEXT` SHALL be inferred when no more-specific type fits.
9. IF all values in a column are null or empty, THE inferred type SHALL be `UNKNOWN`.
10. THE type inference function SHALL be a pure function, independently importable and testable.

---

### REQ-M1-12: Column Profiling

**User Story:** As a data analyst, I need basic quality metrics per column so that I can quickly assess completeness and cardinality without loading the full dataset.

#### Acceptance Criteria

1. FOR each column, THE profiler SHALL compute: `missing_count` (count of null or empty-string values), `unique_count` (count of distinct non-null values), `nullable` (true if `missing_count > 0`).
2. THE profiler SHALL collect up to **5** sample values per column, taken as the first 5 distinct non-null values encountered in row order.
3. Sample values SHALL be stored as their string representation regardless of inferred type.
4. THE profiling function SHALL be a pure function, independently importable and testable.

---

### REQ-M1-13: IngestionJobRepository

**User Story:** As a developer implementing the ingestion service, I need a repository that encapsulates all database access for `IngestionJob`, so that the service layer stays free of raw SQL.

#### Acceptance Criteria

1. THE `IngestionJobRepository` SHALL implement: `create(fields) → IngestionJob`, `get_by_id(job_id) → IngestionJob | None`, `update(job_id, **fields) → IngestionJob`, `list_by_registry(dataset_registry_id, skip, limit) → list[IngestionJob]`.
2. THE repository SHALL follow the existing StatFlow pattern: `__init__(self, session: AsyncSession)`, no `commit()` or `rollback()` calls.
3. THE `update` method SHALL use `setattr` to apply field changes on the fetched ORM object and return it, consistent with existing repository pattern.

---

### REQ-M1-14: DatasetColumnRepository

**User Story:** As a developer implementing column persistence after profiling, I need a repository for `DatasetColumn` records.

#### Acceptance Criteria

1. THE `DatasetColumnRepository` SHALL implement: `bulk_create(columns: list[dict]) → list[DatasetColumn]`, `list_by_job(ingestion_job_id) → list[DatasetColumn]`.
2. `bulk_create` SHALL use a single `session.add_all()` call followed by `session.flush()`.
3. THE repository SHALL follow the existing StatFlow pattern: no `commit()` or `rollback()`.

---

### REQ-M1-15: IngestionService

**User Story:** As a developer wiring up the inspection endpoint, I need a service that orchestrates file parsing, column profiling, job lifecycle management, and result persistence.

#### Acceptance Criteria

1. THE `IngestionService.inspect(file_bytes, filename, content_type, dataset_registry_id, user_id) → IngestionJob` method SHALL:
   a. Create an `IngestionJob` record with status `PENDING`.
   b. Validate format (CSV or XLSX only — HTTP 415 if unsupported).
   c. Validate file size against `INGESTION_MAX_FILE_BYTES` (HTTP 413 if exceeded).
   d. Set status to `RUNNING` and record `started_at`.
   e. Parse the file and extract the header row.
   f. Validate column count against `INGESTION_MAX_COLUMNS` (HTTP 422 if exceeded).
   g. Validate row count against `INGESTION_MAX_ROWS` (HTTP 422 if exceeded).
   h. Normalise column names and deduplicate.
   i. Run type inference and profiling per column.
   j. Persist all `DatasetColumn` records via `DatasetColumnRepository.bulk_create`.
   k. Set status to `COMPLETED`, record `completed_at`, `row_count`, `column_count`.
   l. Return the completed `IngestionJob`.
2. IF any step raises an unrecoverable exception, THE service SHALL set status to `FAILED`, record `failed_at` and `error_message`, and re-raise the exception so the endpoint can return the appropriate HTTP status.
3. THE service SHALL never call `commit()` or `rollback()`.

---

### REQ-M1-16: Pydantic Ingestion Schemas

**User Story:** As a developer defining the API contract for the inspect endpoint, I need typed request and response schemas.

#### Acceptance Criteria

1. THE `IngestionInspectResponse` schema SHALL include: `job_id` (UUID), `status` (IngestionStatus), `original_filename` (string), `file_format` (FileFormat), `file_size_bytes` (integer), `row_count` (integer | null), `column_count` (integer | null), `columns` (list of `DatasetColumnSchema`), `preview_rows` (list of dicts, up to 10, nullable).
2. THE `DatasetColumnSchema` SHALL include: `id` (UUID), `original_name`, `normalized_name`, `inferred_type`, `nullable`, `missing_count`, `unique_count`, `sample_values`.
3. THE `IngestionJobListResponse` schema SHALL include: `jobs` (list of `IngestionJobSummary`), `total` (integer).
4. All schemas SHALL use `ConfigDict(from_attributes=True)` for ORM-model compatibility.

---

### REQ-M1-17: POST /api/v1/ingestion/inspect Endpoint

**User Story:** As a DATA_MANAGER or ADMIN, I want to upload a CSV or XLSX file and receive a structured inspection result, so that I can understand the dataset's structure and quality before committing it to the registry.

#### Acceptance Criteria

1. THE endpoint SHALL be `POST /api/v1/ingestion/inspect` and SHALL accept `multipart/form-data` with fields: `file` (required, UploadFile) and `dataset_registry_id` (optional UUID form field).
2. THE endpoint SHALL require authentication via `get_current_user` and SHALL enforce the `ADMIN` or `DATA_MANAGER` role via `require_data_manager_or_admin`.
3. THE endpoint SHALL require a valid CSRF token via `validate_csrf`.
4. ON success, THE endpoint SHALL return HTTP 200 with an `IngestionInspectResponse`.
5. THE response `preview_rows` field SHALL contain at most 10 rows of raw string values, taken from the start of the data (after the header), or null if the caller did not request a preview.
6. THE endpoint SHALL pass the authenticated user's `id` to `IngestionService.inspect` so it is stored on the `IngestionJob.created_by_user_id`.
7. THE endpoint SHALL map HTTP exceptions raised by `IngestionService` directly to the caller (413, 415, 422 pass through).

---

### REQ-M1-18: Alembic Migration

**User Story:** As a developer applying this spec to an existing database, I need a reversible Alembic migration that creates the new tables and enum types.

#### Acceptance Criteria

1. THE migration SHALL create the `ingestion_status_enum` PostgreSQL type.
2. THE migration SHALL create the `inferred_column_type_enum` PostgreSQL type.
3. THE migration SHALL create the `ingestion_jobs` table with all columns defined in REQ-M1-1.
4. THE migration SHALL create the `dataset_columns` table with all columns defined in REQ-M1-2.
5. WHEN `alembic upgrade head` is run, THE migration SHALL apply without error.
6. WHEN `alembic downgrade -1` is run, THE migration SHALL drop both tables and both enum types without error.

---

### REQ-M1-19: Backend Tests

**User Story:** As a developer, I want a comprehensive backend test suite that validates every layer of the Milestone 1 implementation.

#### Acceptance Criteria

1. THE test suite SHALL include unit tests for the column-name normalisation function covering: all-uppercase input, embedded spaces, leading digits, special characters, empty string, and already-normalised names.
2. THE test suite SHALL include unit tests for duplicate normalised-name deduplication covering: no duplicates (unchanged), one pair, three-way collision, and collision where the suffixed name itself already exists.
3. THE test suite SHALL include unit tests for type inference covering: all seven types, mixed types (falls back to TEXT), all-null column (returns UNKNOWN), and single-value columns for each type.
4. THE test suite SHALL include unit tests for column profiling covering: all-present values, some missing values, all missing, and more than 5 distinct values (sample capped at 5).
5. THE test suite SHALL include integration tests for `IngestionService.inspect` covering: valid CSV (COMPLETED job + correct columns), valid XLSX (COMPLETED job, first sheet only), oversized file (FAILED + 413), too many rows (FAILED + 422), too many columns (FAILED + 422), unsupported format (415), and missing header row.
6. THE test suite SHALL include endpoint integration tests for `POST /api/v1/ingestion/inspect` covering: ADMIN success (200), DATA_MANAGER success (200), unauthenticated (401), ANALYST (403), oversized file (413), unsupported format (415), and malformed CSV (422).
7. THE test suite SHALL include a Hypothesis-based property test (Property 1) verifying that column-name normalisation is idempotent: for any normalised name `n`, `normalise(n) == n`.
8. THE test suite SHALL include a Hypothesis-based property test (Property 2) verifying that type inference is deterministic: for any list of values `vs`, calling `infer_type(vs)` twice returns the same result.
9. WHEN all tests are run, THE test suite SHALL pass with no failures.

---

### REQ-M1-20: Backend Checkpoint

**User Story:** As a developer completing Milestone 1, I need to verify that all new tests pass and that no existing tests have been broken.

#### Acceptance Criteria

1. `pytest backend/tests/` SHALL exit 0 with no failures or errors.
2. The existing auth-foundation tests SHALL still pass after Milestone 1 is applied.

---

## Milestone 2 — Row Persistence

*Full requirements to be detailed when Milestone 1 is complete.*

### Overview

- Approved ingestion jobs transition to row storage: a `DatasetRow` model normalising raw values into typed columns.
- Versioning strategy: each approved import creates a new dataset version; prior versions are retained and queryable.
- Import history endpoint: `GET /api/v1/dataset-registry/{id}/imports` returns a paginated list of `IngestionJob` records.
- Rollback endpoint: `POST /api/v1/ingestion/{job_id}/rollback` marks a version as superseded.
- Query endpoint: `GET /api/v1/datasets/{dataset_id}/rows` with filter, sort, and pagination.

---

## Milestone 3 — Official Dataset Importers

*Full requirements to be detailed when Milestone 2 is complete.*

### Overview

- Publisher-specific adapters for: Zambia Statistics Agency (ZamStats), Bank of Zambia, World Bank, and key Zambian government ministries.
- Each adapter supports both manual trigger (`POST /api/v1/importers/{source}/run`) and scheduled execution (cron-based, configurable interval per source).
- Source provenance fields: `fetched_from_url`, `fetched_at`, `publisher_version`.
- Refresh status tracking on `DatasetRegistry`: `last_checked_at`, `last_refreshed_at`, `refresh_error`.

---

## Milestone 4 — Registry Management UI

*All work from the original spec is retained here, moved from the previous first milestone.*

### Overview

This milestone adds the frontend pages and backend verification endpoint that expose the DataSource and DatasetRegistry catalogues to human users. The full set of requirements from the original spec is preserved:

- **Frontend API service functions** (`api.js`): `fetchDataSources`, `createDataSource`, `updateDataSource`, `deleteDataSource`, `fetchDatasetRegistry`, `createDatasetEntry`, `updateDatasetEntry`, `deleteDatasetEntry`, `verifyDatasetEntry` (original REQ-1).
- **DataSourcesPage** at `/data-sources` with list, client-side search, and role-gated CRUD (original REQ-2, REQ-3).
- **DatasetRegistryPage** at `/dataset-registry` with server-side filters and role-gated CRUD (original REQ-4, REQ-5).
- **Verification workflow backend endpoint** `PATCH /api/v1/dataset-registry/{id}/verify` with `VerificationPermissionError` domain exception (original REQ-6).
- **Verification workflow frontend** action buttons on the registry page (original REQ-7).
- **Router and Sidebar** updates wiring the new pages and implementing navigation links (original REQ-8).
- **Import-to-Registry deep link** on `ImportPage` success panel (original REQ-9).
- **Backend tests** for DataSource/DatasetRegistry CRUD and the verify endpoint (original REQ-10).
- **Alembic migration** for any schema changes (original REQ-11).

All correctness properties from the original spec (Properties 1–6) are retained and apply to this milestone.

---

## Milestone 5 — Organisational Data Intelligence

*Full requirements to be detailed when Milestone 4 is complete.*

### Overview

- Private organisational uploads: a separate `OrganisationDataset` entity with access isolation (row-level ownership).
- Upload UI for organisation administrators.
- Automatic column profiling extended from Milestone 1 infrastructure.
- Automatic visualisation generation (charts) triggered on approved ingestion.
- AI-generated insights: natural-language summary of dataset structure, anomaly flags, and comparison with relevant official benchmarks.
- Comparison API: `GET /api/v1/compare?official={registry_id}&org={org_dataset_id}` returning aligned column mappings and divergence metrics.
