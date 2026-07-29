# Implementation Plan: Official Data Integration

## Overview

This plan is structured across five milestones. **Only Milestone 1 (Ingestion Foundation) is executable now.** Later milestones are listed for planning visibility and will be detailed when the preceding milestone is accepted.

All Milestone 1 tasks are pure backend work. No frontend registry UI is built until Milestone 4.

---

## Milestone 1 — Ingestion Foundation

### Scope constraints (explicit)
- Supported formats: **CSV and XLSX only**.
- XLSX: **first worksheet only**.
- **No full dataset rows are persisted** — only job metadata and column metadata.
- **No charts, no AI insights, no organisation upload UI.**
- Designed to serve both official datasets and future private organisational uploads.

---

## Tasks

- [x] 1. Add `IngestionStatus` and `InferredColumnType` enums + `IngestionJob` and `DatasetColumn` ORM models
  - Create `backend/app/models/ingestion.py`
  - Define `IngestionStatus(str, enum.Enum)`: `PENDING`, `RUNNING`, `COMPLETED`, `FAILED`
  - Define `InferredColumnType(str, enum.Enum)`: `INTEGER`, `FLOAT`, `DATE`, `DATETIME`, `BOOLEAN`, `TEXT`, `UNKNOWN`
  - Define `IngestionJob(Base)` with all columns specified in REQ-M1-1: `id`, `dataset_registry_id` (FK RESTRICT nullable), `status`, `original_filename`, `stored_filename`, `file_format` (reuse existing `FileFormat` enum), `file_size_bytes`, `row_count`, `column_count`, `started_at`, `completed_at`, `failed_at`, `error_message`, `created_by_user_id` (FK SET NULL nullable), `created_at`, `updated_at`
  - Define `DatasetColumn(Base)` with all columns specified in REQ-M1-2: `id`, `ingestion_job_id` (FK CASCADE indexed), `original_name`, `normalized_name`, `inferred_type`, `nullable`, `missing_count`, `unique_count`, `sample_values` (JSON), `created_at`
  - Add `columns` relationship on `IngestionJob` with `cascade="all, delete-orphan"`
  - Import both models in `app/db/base.py`
  - References: REQ-M1-1, REQ-M1-2, REQ-M1-3, REQ-M1-4
  - Acceptance: `python -c "from app.models.ingestion import IngestionJob, DatasetColumn"` exits 0

- [x] 2. Add ingestion configuration to `core/config.py`
  - Add `INGESTION_MAX_FILE_BYTES: int = 10 * 1024 * 1024` to `Settings`
  - Add `INGESTION_MAX_ROWS: int = 100_000`
  - Add `INGESTION_MAX_COLUMNS: int = 500`
  - All three must be overridable via environment variables of the same name
  - References: REQ-M1-6, REQ-M1-7, REQ-M1-8
  - Acceptance: `settings.INGESTION_MAX_FILE_BYTES` returns 10485760 in a clean env

- [x] 3. Implement pure utility functions: column normalisation, deduplication, type inference, column profiling
  - Create `backend/app/utils/ingestion_utils.py`
  - Implement `normalise_column_name(raw: str, position: int = 1) -> str` per REQ-M1-9 algorithm: strip → lower → collapse whitespace to `_` → strip non-word chars → collapse `__` → strip edge `_` → prepend `col_` if starts with digit → use `col_<position>` if empty
  - Implement `deduplicate_names(names: list[str]) -> list[str]` per REQ-M1-10: left-to-right, suffix `_2`, `_3` … on collision
  - Implement `infer_type(values: list[str | None]) -> InferredColumnType` per REQ-M1-11: test BOOLEAN → INTEGER → FLOAT → DATE → DATETIME → TEXT; return UNKNOWN if all null
  - Implement `profile_column(values: list[str | None]) -> ColumnProfile` per REQ-M1-12: `missing_count`, `unique_count`, `nullable`, `sample_values` (≤5 distinct non-null)
  - All four functions must be pure (no side effects, no I/O, no DB access)
  - References: REQ-M1-9, REQ-M1-10, REQ-M1-11, REQ-M1-12
  - Acceptance: unit tests in Task 7 pass against these functions

- [x] 4. Implement CSV parser and XLSX parser
  - Create or extend `backend/app/utils/xlsx_parser.py`
  - `XlsxParser.parse(raw_bytes: bytes) -> ParseResult` — load with `openpyxl`, access `workbook.worksheets[0]` (first sheet only), first non-empty row is the header, all cell values cast to `str`, `None` cells become `""`; add `openpyxl` to `requirements.txt` if not already present
  - Ensure existing CSV parsing is accessible as a `ParseResult`-returning function: `header: list[str]`, `rows: list[list[str]]`; UTF-8 with BOM stripping, latin-1 fallback, strip whitespace from each cell
  - Both parsers must return a consistent `ParseResult` dataclass (or named tuple) so `IngestionService` can treat both uniformly
  - References: REQ-M1-5
  - Acceptance: `XlsxParser().parse(bytes_of_simple_xlsx)` returns correct header + rows; CSV parsing returns expected values

- [ ] 5. Implement `IngestionJobRepository` and `DatasetColumnRepository`
  - Create `backend/app/repositories/ingestion_job_repository.py`
    - `IngestionJobRepository.__init__(self, session: AsyncSession)`
    - `async create(self, **fields) -> IngestionJob` — `session.add` + `flush`
    - `async get_by_id(self, job_id: UUID) -> IngestionJob | None`
    - `async update(self, job_id: UUID, **fields) -> IngestionJob` — fetch, `setattr`, return
    - `async list_by_registry(self, dataset_registry_id: UUID, skip: int, limit: int) -> list[IngestionJob]`
  - Create `backend/app/repositories/dataset_column_repository.py`
    - `DatasetColumnRepository.__init__(self, session: AsyncSession)`
    - `async bulk_create(self, columns: list[dict]) -> list[DatasetColumn]` — `session.add_all` + `flush`
    - `async list_by_job(self, ingestion_job_id: UUID) -> list[DatasetColumn]`
  - No `commit()` or `rollback()` in either repository
  - References: REQ-M1-13, REQ-M1-14
  - Acceptance: used successfully by IngestionService in Task 6

- [ ] 6. Implement `IngestionService`
  - Create `backend/app/services/ingestion_service.py`
  - `IngestionService.__init__(self, session: AsyncSession)`
  - `async inspect(self, file_bytes: bytes, filename: str, content_type: str | None, dataset_registry_id: UUID | None, user_id: UUID | None) -> IngestionJob` implementing the full orchestration from REQ-M1-15:
    1. Create `IngestionJob` with status `PENDING`
    2. Detect format from content_type + extension; raise `HTTPException(415)` if not CSV or XLSX
    3. Validate file size; raise `HTTPException(413)` if exceeded
    4. Set status `RUNNING`, `started_at = now()`
    5. Parse file via `CsvParser` or `XlsxParser`
    6. Validate column count; raise `HTTPException(422)` if exceeded
    7. Validate row count; raise `HTTPException(422)` if exceeded
    8. Normalise and deduplicate column names
    9. Infer type + profile each column
    10. `DatasetColumnRepository.bulk_create(column_records)`
    11. Set status `COMPLETED`, `completed_at`, `row_count`, `column_count`
    12. Return the updated `IngestionJob`
  - On any unrecoverable exception: set status `FAILED`, `failed_at`, `error_message`, then re-raise
  - Never calls `commit()` or `rollback()`
  - Also store up to 10 preview rows on the job or return them directly (used by endpoint)
  - References: REQ-M1-15
  - Acceptance: integration tests in Task 8 pass

- [ ] 7. Add Pydantic ingestion schemas
  - Create `backend/app/schemas/ingestion.py`
  - `DatasetColumnSchema(BaseModel)`: `id`, `original_name`, `normalized_name`, `inferred_type`, `nullable`, `missing_count`, `unique_count`, `sample_values`; `ConfigDict(from_attributes=True)`
  - `IngestionInspectResponse(BaseModel)`: `job_id`, `status`, `original_filename`, `file_format`, `file_size_bytes`, `row_count`, `column_count`, `columns: list[DatasetColumnSchema]`, `preview_rows: Optional[list[dict[str, str]]]`; `ConfigDict(from_attributes=True)`
  - `IngestionJobSummary(BaseModel)`: `id`, `status`, `original_filename`, `file_format`, `file_size_bytes`, `row_count`, `column_count`, `started_at`, `completed_at`, `failed_at`, `error_message`, `created_at`; `ConfigDict(from_attributes=True)`
  - `IngestionJobListResponse(BaseModel)`: `jobs: list[IngestionJobSummary]`, `total: int`
  - References: REQ-M1-16
  - Acceptance: `IngestionInspectResponse.model_validate(completed_job_orm_instance)` succeeds

- [ ] 8. Implement `POST /api/v1/ingestion/inspect` endpoint and register router
  - Create `backend/app/api/v1/endpoints/ingestion.py`
  - `router = APIRouter(prefix="/ingestion", tags=["Ingestion"])`
  - `POST /ingestion/inspect`: accept `file: UploadFile = File(...)` and `dataset_registry_id: Optional[UUID] = Form(None)` (multipart form); guards: `get_current_user`, `require_data_manager_or_admin`, `validate_csrf`
  - Read file bytes, call `IngestionService(db).inspect(...)`, map to `IngestionInspectResponse`
  - HTTP exceptions (413, 415, 422) raised by the service pass through directly
  - Register `ingestion.router` in `app/api/v1/api.py`
  - References: REQ-M1-17
  - Acceptance: endpoint integration tests in Task 9 pass

- [ ] 9. Write Alembic migration for ingestion foundation
  - Run `alembic revision --autogenerate -m "ingestion_foundation"` from `backend/`
  - Review generated migration; confirm it creates `ingestion_status_enum`, `inferred_column_type_enum`, `ingestion_jobs` table, `dataset_columns` table
  - Manually adjust if autogenerate misses enum creation (common with native PostgreSQL enums)
  - Verify `alembic upgrade head` runs cleanly on a fresh schema
  - Verify `alembic downgrade -1` drops both tables and both enum types cleanly
  - References: REQ-M1-18
  - Acceptance: both `upgrade` and `downgrade` exit 0 without error

- [ ] 10. Write unit tests for pure utility functions
  - Create `backend/tests/test_ingestion.py`
  - `normalise_column_name`: all-uppercase, embedded spaces, leading digit, special characters, empty string, already-normalised input
  - `deduplicate_names`: no duplicates (unchanged), one pair (suffix `_2`), three-way collision (suffix `_2`, `_3`), collision where the suffixed name itself already exists
  - `infer_type`: each of the 7 types with representative values, mixed types (→ TEXT), all-null (→ UNKNOWN), single-value column for each type
  - `profile_column`: all present, some missing, all missing, >5 distinct values (sample capped at 5)
  - `CsvParser.parse`: basic valid CSV, quoted fields, UTF-8 BOM, empty file
  - `XlsxParser.parse`: basic XLSX, first-sheet-only (second sheet has different columns and must be ignored)
  - **Property 1 (Hypothesis):** `normalise_column_name` is idempotent — `@given(st.text())`, 500 iterations
  - **Property 2 (Hypothesis):** `infer_type` is deterministic — `@given(st.lists(...))`, 300 iterations
  - **Property 3 (Hypothesis):** `deduplicate_names` output has no duplicates — `@given(st.lists(st.text(min_size=1)))`, 300 iterations
  - References: REQ-M1-19.1–REQ-M1-19.4, REQ-M1-19.7–REQ-M1-19.8
  - Acceptance: all unit and property tests in this file pass

- [ ] 11. Write integration tests for `IngestionService` and the inspect endpoint
  - In `backend/tests/test_ingestion.py` (same file, new test classes/functions)
  - **Service tests (real DB, `db_session` fixture):**
    - Valid CSV (100 rows, 5 columns) → COMPLETED job, 5 `DatasetColumn` records with correct names and types
    - Valid XLSX (two sheets) → COMPLETED job, columns from first sheet only
    - Duplicate column headers in CSV → COMPLETED job, deduplicated `normalized_name` values
    - All-null column → `inferred_type=UNKNOWN`, `nullable=True`
    - File > `INGESTION_MAX_FILE_BYTES` → HTTPException 413
    - Row count > `INGESTION_MAX_ROWS` → HTTPException 422
    - Column count > `INGESTION_MAX_COLUMNS` → HTTPException 422
    - Unsupported format bytes with `content_type="application/pdf"` → HTTPException 415
    - `dataset_registry_id` referencing a valid registry entry → `IngestionJob.dataset_registry_id` populated
  - **Endpoint tests (`client` fixture, `httpx.AsyncClient`):**
    - ADMIN uploads valid CSV → 200 with `IngestionInspectResponse`
    - DATA_MANAGER uploads valid XLSX → 200
    - Unauthenticated → 401
    - ANALYST role → 403
    - VIEWER role → 403
    - Missing CSRF → 403
    - File > 10 MB → 413
    - PDF content type → 415
    - Row count > 100k → 422
    - Column count > 500 → 422
  - **Property 4 (Hypothesis, endpoint-level):** any byte string larger than `INGESTION_MAX_FILE_BYTES` submitted to the endpoint returns 413
  - References: REQ-M1-19.5, REQ-M1-19.6, REQ-M1-19.9
  - Acceptance: all integration tests pass

- [ ] 12. Backend checkpoint — full regression suite
  - Run `pytest backend/tests/` from `backend/`
  - All existing auth-foundation tests must still pass
  - All new ingestion tests must pass
  - Zero failures, zero errors
  - References: REQ-M1-20
  - Acceptance: `pytest` exits 0

---

## Task Dependency Graph

```json
{
  "waves": [
    { "wave": 1, "tasks": ["1", "2"] },
    { "wave": 2, "tasks": ["3", "4", "5"] },
    { "wave": 3, "tasks": ["6", "7"] },
    { "wave": 4, "tasks": ["8", "9", "10"] },
    { "wave": 5, "tasks": ["11"] },
    { "wave": 6, "tasks": ["12"] }
  ]
}
```

Wave 1: models and configuration (no dependencies).
Wave 2: pure utilities, parsers, and repositories (depend on models).
Wave 3: service and schemas (depend on repositories and utilities).
Wave 4: endpoint, migration, and unit tests (depend on service and schemas).
Wave 5: integration tests (depend on endpoint, migration, and unit tests being in place).
Wave 6: regression checkpoint (depends on everything).

---

## Milestone 2 — Row Persistence

*Not executable yet. To be detailed after Milestone 1 acceptance.*

Planned tasks (subject to revision):
- [ ] M2-1. Add `DatasetVersion` and `DatasetRow` ORM models + migration
- [ ] M2-2. Implement `DatasetRowRepository` and `DatasetVersionRepository`
- [ ] M2-3. Implement `IngestionApprovalService` (creates version + persists rows as background task)
- [ ] M2-4. Add `POST /api/v1/ingestion/{job_id}/approve` endpoint
- [ ] M2-5. Add `POST /api/v1/ingestion/{job_id}/rollback` endpoint
- [ ] M2-6. Add `GET /api/v1/datasets/{dataset_id}/rows` query endpoint
- [ ] M2-7. Write backend tests for row persistence and querying
- [ ] M2-8. Backend checkpoint

---

## Milestone 3 — Official Dataset Importers

*Not executable yet. To be detailed after Milestone 2 acceptance.*

Planned tasks:
- [ ] M3-1. Define `DataPublisherAdapter` abstract base class
- [ ] M3-2. Implement `ZamStatsAdapter`
- [ ] M3-3. Implement `BankOfZambiaAdapter`
- [ ] M3-4. Implement `WorldBankAdapter`
- [ ] M3-5. Implement `MinistryAdapter` (generic)
- [ ] M3-6. Add scheduler wiring (APScheduler or Celery Beat)
- [ ] M3-7. Add manual trigger endpoint `POST /api/v1/importers/{source}/run`
- [ ] M3-8. Add provenance fields to `IngestionJob` + migration
- [ ] M3-9. Write backend tests and checkpoint

---

## Milestone 4 — Registry Management UI

*Not executable yet. To be detailed after Milestone 3 acceptance. All work from the original spec is retained here.*

Planned tasks (ported from original spec):
- [ ] M4-1. Add `verify_dataset` service method + `VerificationPermissionError` + `/verify` endpoint
- [ ] M4-2. Write backend tests for verification endpoint and DataSource/DatasetRegistry CRUD
- [ ] M4-3. Backend checkpoint
- [ ] M4-4. Add Alembic migration (no-op or schema change)
- [ ] M4-5. Add frontend API service functions to `api.js` (9 new exports)
- [ ] M4-6. Implement `DataSourcesPage` + `DataSourceFormModal`
- [ ] M4-7. Implement `DatasetRegistryPage` + `DatasetRegistryFormModal`
- [ ] M4-8. Implement router + Sidebar wiring
- [ ] M4-9. Add "View in Dataset Registry" link to `ImportPage` success panel
- [ ] M4-10. Write frontend tests (unit + property-based, Properties 1–4, 6)
- [ ] M4-11. Final checkpoint (pytest + vitest)

---

## Milestone 5 — Organisational Data Intelligence

*Not executable yet. To be detailed after Milestone 4 acceptance.*

Planned tasks:
- [ ] M5-1. `Organisation` + `OrganisationDataset` models + migration
- [ ] M5-2. Row-level access isolation middleware/dependency
- [ ] M5-3. Organisation upload endpoint + UI
- [ ] M5-4. Extended column profiling (min, max, mean, std_dev)
- [ ] M5-5. Chart generation pipeline (`DatasetChart` table)
- [ ] M5-6. AI insights endpoint + `DatasetInsight` table
- [ ] M5-7. Comparison API
- [ ] M5-8. Full test suite and checkpoint

---

## Notes

- All Milestone 1 backend code follows the existing StatFlow conventions: FastAPI async endpoints, SQLAlchemy async sessions, repository pattern with no `commit()`/`rollback()` in the service layer.
- `openpyxl` must be added to `backend/requirements.txt` if not already present (check before Task 4).
- `hypothesis` must be added to `backend/requirements-dev.txt` (or `requirements.txt`) before Task 10.
- The existing `FileFormat` enum (CSV, XLSX, JSON, API, OTHER) from `data_source.py` is reused on `IngestionJob.file_format` — no new enum needed for file format.
- Property tests reference the design document property number and the requirements clause they validate.
- Milestone 4 retains all correctness properties from the original spec (Properties 1–6 in the design document).
