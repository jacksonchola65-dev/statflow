# Design Document: Official Data Integration

## Overview

This feature is structured into five milestones. The design below covers **Milestone 1 — Ingestion Foundation** in full. Later milestones are outlined at an architecture level and will be detailed in subsequent spec revisions.

**Milestone 1 scope boundary (explicit):**
- Supported input formats: **CSV and XLSX only**.
- For XLSX: **only the first worksheet** is inspected.
- **Full dataset rows are not persisted.** Only ingestion job metadata and per-column profiles are stored.
- **No charts are generated.**
- **No AI insights are generated.**
- **No organisational upload UI is built.**
- The design is intentionally format-agnostic and dual-purpose: it serves both official government datasets and future private organisational uploads (Milestone 5) through the same `IngestionJob` / `DatasetColumn` infrastructure.

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│  FastAPI  /api/v1/ingestion                                         │
│                                                                     │
│  POST /ingestion/inspect                                            │
│       │                                                             │
│  IngestionEndpoint                                                  │
│       │  multipart file + dataset_registry_id                       │
│       ▼                                                             │
│  IngestionService.inspect(file_bytes, filename, content_type, ...)  │
│       │                                                             │
│       ├─► format_detector.detect(content_type, filename) → FileFormat
│       ├─► size_guard.check(len(bytes), settings.INGESTION_MAX_FILE_BYTES)
│       │                                                             │
│       ├─► CsvParser.parse(bytes)  → ParseResult                    │
│       │   OR                                                        │
│       │   XlsxParser.parse(bytes) → ParseResult  (first sheet only)│
│       │                                                             │
│       │   ParseResult { header: list[str], rows: list[list[str]] } │
│       │                                                             │
│       ├─► column_count_guard.check(len(header), settings.MAX_COLS) │
│       ├─► row_count_guard.check(len(rows), settings.MAX_ROWS)      │
│       │                                                             │
│       ├─► normalise_column_names(header) → list[str]               │
│       ├─► deduplicate_names(list[str])   → list[str]               │
│       │                                                             │
│       ├─► for each column:                                          │
│       │      infer_type(values)  → InferredColumnType               │
│       │      profile_column(values) → ColumnProfile                 │
│       │                                                             │
│       ├─► IngestionJobRepository.update(job, COMPLETED)            │
│       ├─► DatasetColumnRepository.bulk_create(column_records)      │
│       └─► return IngestionJob                                       │
│                                                                     │
│  Repositories  (AsyncSession, no commit/rollback)                  │
│  IngestionJobRepository   DatasetColumnRepository                   │
│                                                                     │
│  PostgreSQL                                                         │
│  ingestion_jobs    dataset_columns                                  │
└─────────────────────────────────────────────────────────────────────┘
```

---

## New File Map

### Backend — Milestone 1

```
backend/app/
├── models/
│   └── ingestion.py                 NEW — IngestionJob, DatasetColumn, enums
├── repositories/
│   ├── ingestion_job_repository.py  NEW — CRUD for IngestionJob
│   └── dataset_column_repository.py NEW — bulk_create, list_by_job
├── services/
│   └── ingestion_service.py         NEW — orchestrates parse → profile → persist
├── schemas/
│   └── ingestion.py                 NEW — IngestionInspectResponse, DatasetColumnSchema, etc.
├── api/v1/endpoints/
│   └── ingestion.py                 NEW — POST /ingestion/inspect
├── api/v1/api.py                    UPDATED — register ingestion.router
├── core/config.py                   UPDATED — add INGESTION_MAX_FILE_BYTES, INGESTION_MAX_ROWS, INGESTION_MAX_COLUMNS
├── utils/
│   ├── csv_parser.py                UPDATED — extend existing parser or create ingestion-specific variant
│   └── xlsx_parser.py               NEW — parse first sheet of XLSX to ParseResult
└── alembic/versions/
    └── <timestamp>_ingestion_foundation.py  NEW — creates enums + tables
```

```
backend/tests/
└── test_ingestion.py                NEW — all Milestone 1 tests
```

---

## Data Models

### `IngestionStatus` enum

```python
class IngestionStatus(str, enum.Enum):
    PENDING   = "PENDING"
    RUNNING   = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED    = "FAILED"
```

### `InferredColumnType` enum

```python
class InferredColumnType(str, enum.Enum):
    INTEGER  = "INTEGER"
    FLOAT    = "FLOAT"
    DATE     = "DATE"
    DATETIME = "DATETIME"
    BOOLEAN  = "BOOLEAN"
    TEXT     = "TEXT"
    UNKNOWN  = "UNKNOWN"
```

### `IngestionJob` ORM model

```python
class IngestionJob(Base):
    __tablename__ = "ingestion_jobs"

    id: Mapped[uuid.UUID]                          # PK
    dataset_registry_id: Mapped[Optional[uuid.UUID]]  # FK → dataset_registry.id RESTRICT
    status: Mapped[IngestionStatus]                # not null
    original_filename: Mapped[str]                 # not null
    stored_filename: Mapped[Optional[str]]         # reserved for future file storage
    file_format: Mapped[FileFormat]                # reuses existing enum
    file_size_bytes: Mapped[int]                   # not null
    row_count: Mapped[Optional[int]]               # null until parsing completes
    column_count: Mapped[Optional[int]]            # null until parsing completes
    started_at: Mapped[Optional[datetime]]
    completed_at: Mapped[Optional[datetime]]
    failed_at: Mapped[Optional[datetime]]
    error_message: Mapped[Optional[str]]           # text
    created_by_user_id: Mapped[Optional[uuid.UUID]]  # FK → users.id SET NULL
    created_at: Mapped[datetime]                   # server default now()
    updated_at: Mapped[datetime]                   # auto-updated

    # Relationship
    columns: Mapped[List["DatasetColumn"]]         # cascade="all, delete-orphan"
```

### `DatasetColumn` ORM model

```python
class DatasetColumn(Base):
    __tablename__ = "dataset_columns"

    id: Mapped[uuid.UUID]                          # PK
    ingestion_job_id: Mapped[uuid.UUID]            # FK → ingestion_jobs.id CASCADE, indexed
    original_name: Mapped[str]                     # raw header from file
    normalized_name: Mapped[str]                   # deterministic normalised form
    inferred_type: Mapped[InferredColumnType]      # not null
    nullable: Mapped[bool]                         # true if any missing values
    missing_count: Mapped[int]                     # default 0
    unique_count: Mapped[int]                      # default 0
    sample_values: Mapped[Optional[list]]          # JSON, up to 5 values
    created_at: Mapped[datetime]                   # server default now()
```

---

## Core Algorithms

### Column-Name Normalisation

Pure function `normalise_column_name(raw: str) -> str`:

```python
def normalise_column_name(raw: str, position: int = 1) -> str:
    s = raw.strip()
    s = s.lower()
    s = re.sub(r'\s+', '_', s)          # collapse whitespace to underscore
    s = re.sub(r'[^\w]', '', s)         # strip non-word characters (keeps letters, digits, _)
    s = re.sub(r'_+', '_', s)           # collapse multiple underscores
    s = s.strip('_')                    # strip leading/trailing underscores
    if s and s[0].isdigit():
        s = 'col_' + s
    if not s:
        s = f'col_{position}'
    return s
```

**Design property:** This function is idempotent — `normalise(normalise(x)) == normalise(x)` for all inputs.

### Duplicate Normalised-Name Deduplication

Pure function `deduplicate_names(names: list[str]) -> list[str]`:

- Iterate left to right over normalised names.
- Maintain a `seen: dict[str, int]` tracking count of each name seen so far.
- If the current name is not in `seen`, add it unchanged.
- If the name is already in `seen`, suffix with `_<n+1>` and repeat until the suffixed name is also unique.

### Type Inference

Pure function `infer_type(values: list[str | None]) -> InferredColumnType`:

- Filter out null and empty-string values → `non_null`.
- If `non_null` is empty → `UNKNOWN`.
- Test candidates in order: `BOOLEAN`, `INTEGER`, `FLOAT`, `DATE`, `DATETIME`.
- Return the first type that fits all `non_null` values; fall back to `TEXT`.

Type-fit predicates:
- `BOOLEAN`: `v.lower() in {"true","false","yes","no","1","0"}`
- `INTEGER`: `int(v)` succeeds and `'.' not in v`
- `FLOAT`: `float(v)` succeeds
- `DATE`: `datetime.strptime(v, "%Y-%m-%d")` succeeds
- `DATETIME`: `datetime.fromisoformat(v)` succeeds

### Column Profiling

Pure function `profile_column(values: list[str | None]) -> ColumnProfile`:

```python
@dataclass
class ColumnProfile:
    missing_count: int
    unique_count: int
    nullable: bool
    sample_values: list[str]  # up to 5
```

- `missing_count` = count of `None` or `""` values.
- `unique_count` = count of distinct non-null non-empty values.
- `nullable` = `missing_count > 0`.
- `sample_values` = first 5 distinct non-null non-empty values in row order.

### File Parsing

**CsvParser** (extend or wrap existing `csv_parser.py`):

```python
@dataclass
class ParseResult:
    header: list[str]
    rows: list[list[str]]     # all rows as strings, header excluded

class CsvParser:
    def parse(self, raw_bytes: bytes) -> ParseResult: ...
```

- Decode with UTF-8 (with BOM stripping); fall back to latin-1.
- Use Python `csv.reader` with auto-dialect detection.
- Strip surrounding whitespace from each cell value.

**XlsxParser** (new):

```python
class XlsxParser:
    def parse(self, raw_bytes: bytes) -> ParseResult: ...
```

- Load with `openpyxl` (already available in many Python environments; add to `requirements.txt` if absent).
- Access `workbook.worksheets[0]` — first sheet only.
- Treat the first non-empty row as the header.
- Convert all cell values to `str`; treat `None` cells as empty string.

---

## Pydantic Schemas

```python
# schemas/ingestion.py

class DatasetColumnSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    original_name: str
    normalized_name: str
    inferred_type: InferredColumnType
    nullable: bool
    missing_count: int
    unique_count: int
    sample_values: Optional[list[str]]

class IngestionInspectResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    job_id: uuid.UUID
    status: IngestionStatus
    original_filename: str
    file_format: FileFormat
    file_size_bytes: int
    row_count: Optional[int]
    column_count: Optional[int]
    columns: list[DatasetColumnSchema]
    preview_rows: Optional[list[dict[str, str]]]  # up to 10 rows

class IngestionJobSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: uuid.UUID
    status: IngestionStatus
    original_filename: str
    file_format: FileFormat
    file_size_bytes: int
    row_count: Optional[int]
    column_count: Optional[int]
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    failed_at: Optional[datetime]
    error_message: Optional[str]
    created_at: datetime

class IngestionJobListResponse(BaseModel):
    jobs: list[IngestionJobSummary]
    total: int
```

---

## Endpoint Contract

```
POST /api/v1/ingestion/inspect
  Auth:    Bearer cookie (get_current_user) + require_data_manager_or_admin + validate_csrf
  Body:    multipart/form-data
           file:                UploadFile  (required)
           dataset_registry_id: UUID        (optional form field)
  
  200 OK → IngestionInspectResponse
  401    → unauthenticated
  403    → insufficient role or CSRF failure
  413    → file exceeds INGESTION_MAX_FILE_BYTES
  415    → unsupported file format (not CSV or XLSX)
  422    → row or column count limit exceeded; also malformed file
```

---

## Configuration (`core/config.py`)

```python
# New fields added to Settings:
INGESTION_MAX_FILE_BYTES: int = 10 * 1024 * 1024   # 10 MB
INGESTION_MAX_ROWS:       int = 100_000
INGESTION_MAX_COLUMNS:    int = 500
```

All three are overridable via environment variables of the same name.

---

## Alembic Migration Strategy

The migration creates two new PostgreSQL enum types and two new tables:

1. `CREATE TYPE ingestion_status_enum AS ENUM ('PENDING','RUNNING','COMPLETED','FAILED')`
2. `CREATE TYPE inferred_column_type_enum AS ENUM ('INTEGER','FLOAT','DATE','DATETIME','BOOLEAN','TEXT','UNKNOWN')`
3. `CREATE TABLE ingestion_jobs (...)` with FK to `dataset_registry` (RESTRICT) and `users` (SET NULL).
4. `CREATE TABLE dataset_columns (...)` with FK to `ingestion_jobs` (CASCADE).

Down migration drops tables first (CASCADE), then drops enum types.

The existing `file_format_enum` is **reused** on `ingestion_jobs.file_format` — no new enum needed.

---

## Correctness Properties

### Property 1: Column-Name Normalisation is Idempotent

*For any string `s`*, `normalise_column_name(normalise_column_name(s)) == normalise_column_name(s)`.

Applying normalisation twice produces the same result as applying it once. This guarantees that downstream systems that normalise already-normalised names get stable identifiers.

**Implementation:** Hypothesis `@given(st.text())` strategy, 500 iterations minimum.
**Validates: REQ-M1-9**

### Property 2: Type Inference is Deterministic

*For any list of string-or-None values `vs`*, `infer_type(vs) == infer_type(vs)` (calling twice returns the same result). Also: `infer_type(vs + vs) == infer_type(vs)` — adding duplicate rows does not change the inferred type.

**Implementation:** Hypothesis `@given(st.lists(st.one_of(st.none(), st.text())))`, 300 iterations minimum.
**Validates: REQ-M1-11**

### Property 3: Deduplication Produces Unique Names

*For any list of strings `names`*, the output of `deduplicate_names(names)` SHALL have no duplicate entries: `len(output) == len(set(output))`.

**Implementation:** Hypothesis `@given(st.lists(st.text(min_size=1)))`, 300 iterations minimum.
**Validates: REQ-M1-10**

### Property 4: File-Size Limit is Always Enforced

*For any byte string `b` with `len(b) > INGESTION_MAX_FILE_BYTES`*, calling `POST /ingestion/inspect` SHALL return HTTP 413 regardless of the file's actual content or format.

**Implementation:** Hypothesis `@given(st.binary(min_size=INGESTION_MAX_FILE_BYTES+1))`, 50 iterations (file generation is expensive).
**Validates: REQ-M1-6**

### Property 5: Verification Role-Permission Matrix (Milestone 4)

*Retained from original spec.* For any `(calling_role, target_status)` pair, the `/verify` endpoint returns 200 iff the pair is in `{(ADMIN, VERIFIED), (ADMIN, REJECTED), (DATA_MANAGER, PENDING)}`; returns 403 for all other authenticated combinations.

**Validates: Original REQ-6 (now Milestone 4)**

### Property 6: Import Success Link Conditionality (Milestone 4)

*Retained from original spec.* The `ImportPage` success panel shows "View in Dataset Registry" iff `dataset_ids.length > 0`.

**Validates: Original REQ-9 (now Milestone 4)**

---

## Testing Strategy

### Milestone 1 backend tests (`backend/tests/test_ingestion.py`)

All tests use the existing `pytest-asyncio` + real PostgreSQL test database fixtures established in `conftest.py`.

**Unit tests (pure functions — no DB, no fixtures):**

| Test group | Coverage |
|---|---|
| `normalise_column_name` | uppercase, spaces, leading digit, special chars, empty, already-normalised |
| `deduplicate_names` | no dupes, one pair, three-way collision, suffixed name collision |
| `infer_type` | each of 7 types, mixed (→ TEXT), all-null (→ UNKNOWN), single value per type |
| `profile_column` | all present, some missing, all missing, >5 distinct (sample capped) |
| `CsvParser.parse` | basic CSV, quoted fields, BOM, empty file |
| `XlsxParser.parse` | basic XLSX, first-sheet-only, empty sheet |

**Service integration tests (real DB):**

| Scenario | Expected outcome |
|---|---|
| Valid CSV, 100 rows, 5 columns | COMPLETED job, 5 DatasetColumn records |
| Valid XLSX, second sheet has different columns | COMPLETED job, first-sheet columns only |
| File too large | HTTP 413, FAILED job (or no job if size check is pre-DB) |
| Row count exceeds limit | HTTP 422, FAILED job |
| Column count exceeds limit | HTTP 422, FAILED job |
| Unsupported format (PDF) | HTTP 415 |
| CSV with duplicate column headers | COMPLETED, deduplicated names in DatasetColumn |
| All-null column | COMPLETED, `inferred_type=UNKNOWN`, `nullable=True` |
| `dataset_registry_id` provided (valid) | `IngestionJob.dataset_registry_id` populated |
| `dataset_registry_id` not found | HTTP 422 (or 404 — service validates FK) |

**Endpoint integration tests (`httpx.AsyncClient`):**

| Scenario | Expected status |
|---|---|
| ADMIN uploads valid CSV | 200 |
| DATA_MANAGER uploads valid XLSX | 200 |
| Unauthenticated | 401 |
| ANALYST role | 403 |
| VIEWER role | 403 |
| Missing CSRF | 403 |
| File > 10 MB | 413 |
| `.pdf` content type | 415 |
| Row count > 100k | 422 |
| Column count > 500 | 422 |

**Property-based tests (Hypothesis):**

- Property 1: Normalisation idempotency (500 iterations)
- Property 2: Type inference determinism (300 iterations)
- Property 3: Deduplication uniqueness (300 iterations)
- Property 4: File-size limit always enforced (50 iterations)

---

## Milestone 2 — Row Persistence (outline)

*Full design to follow after Milestone 1 acceptance.*

- `DatasetRow` model: `id`, `ingestion_job_id`, `row_index`, `data` (JSONB — column normalised_name → typed value).
- `DatasetVersion` model: links a `DatasetRegistry` entry to an approved `IngestionJob`; carries `is_active` flag.
- Approval endpoint: `POST /api/v1/ingestion/{job_id}/approve` — creates `DatasetVersion`, triggers row persistence as a background task.
- Rollback: `POST /api/v1/ingestion/{job_id}/rollback` — marks the active version as superseded.
- Row query: `GET /api/v1/datasets/{dataset_id}/rows?page&page_size&filter`.

---

## Milestone 3 — Official Dataset Importers (outline)

*Full design to follow after Milestone 2 acceptance.*

- Abstract `DataPublisherAdapter` base class with `fetch() → bytes` and `metadata() → dict`.
- Concrete adapters: `ZamStatsAdapter`, `BankOfZambiaAdapter`, `WorldBankAdapter`, `MinistryAdapter`.
- Scheduler: APScheduler (or Celery Beat) calling `IngestionService.inspect()` then `approve()` automatically if verification passes.
- Provenance fields added to `IngestionJob`: `source_url`, `source_fetched_at`, `publisher_reference`.

---

## Milestone 4 — Registry Management UI (outline)

*All design from the original spec is retained here.*

The full design of `DataSourcesPage`, `DatasetRegistryPage`, form modals, `Sidebar` wiring, router updates, verification endpoint and service method, and all frontend correctness properties (Properties 1–4, 6) are preserved from the prior spec version and will be written in full when this milestone is scheduled.

**Key interface carried forward:**
- `PATCH /api/v1/dataset-registry/{id}/verify` with `VerificationPermissionError`
- `verify_dataset(entry_id, status, calling_role)` service method
- 9 new `api.js` exported functions
- `Sidebar` NavLink implementation (role-gated)
- `ImportPage` "View in Dataset Registry" deep link

---

## Milestone 5 — Organisational Data Intelligence (outline)

*Full design to follow after Milestone 4 acceptance.*

- `Organisation` model: `id`, `name`, `slug`, `owner_user_id`, `is_active`.
- `OrganisationDataset` model: `id`, `organisation_id`, `ingestion_job_id`, `access_level` (PRIVATE | SHARED | PUBLIC).
- Row-level access isolation: all queries filter by `organisation_id` derived from the authenticated user's organisation membership.
- Automatic profiling: extended `DatasetColumn` with `min_value`, `max_value`, `mean`, `std_dev` (for numeric columns).
- Chart generation: triggered post-approval; stores chart spec (Vega-Lite JSON) in a `DatasetChart` table.
- AI insights: `POST /api/v1/datasets/{id}/insights` → calls an LLM with column metadata and profile; stores result in `DatasetInsight` table.
- Comparison API: column alignment by normalised name; divergence metric per aligned column.
