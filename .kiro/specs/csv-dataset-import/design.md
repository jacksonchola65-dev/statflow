# Design: CSV Dataset Import Foundation

## Overview

A new vertical slice added to StatFlow. The backend gains two endpoints, a CSV parser/validator, an import service, and a repository extension. The frontend gains a new `/import` route with a three-state page (Upload → Preview → Success). No existing files are modified except `api.py` (router registration) and the frontend router.

---

## File Changes

### Backend

```
backend/app/
├── api/v1/
│   ├── api.py                          UPDATED — register imports router
│   └── endpoints/
│       └── imports.py                  NEW — preview + confirm endpoints
├── schemas/
│   └── imports.py                      NEW — request/response Pydantic models
├── services/
│   └── import_service.py               NEW — orchestrates parse → validate → store
├── repositories/
│   └── import_repository.py            NEW — bulk insert + conflict check queries
└── utils/
    └── csv_parser.py                   NEW — CSV parsing + row-level validation
```

### Frontend

```
frontend/src/
├── app/
│   └── router.jsx                      UPDATED — add /import route
├── pages/
│   └── ImportPage.jsx                  NEW — three-state upload/preview/success page
├── components/
│   └── import/
│       ├── DropZone.jsx                NEW — drag-and-drop file input
│       ├── PreviewSummary.jsx          NEW — count badges
│       ├── ValidationErrorTable.jsx   NEW — error rows table
│       └── SampleRecordsTable.jsx      NEW — valid sample rows table
└── services/
    └── api.js                          UPDATED — add importPreview + importConfirm
```

---

## Backend Architecture

### Endpoint Layer (`imports.py`)

Two FastAPI route handlers only. No business logic, no database access.

```python
@router.post("/imports/csv/preview", response_model=CsvPreviewResponse)
async def preview_csv(file: UploadFile = File(...), db: AsyncSession = Depends(get_db)):
    # 1. Size + MIME guard (raises HTTP 413/415/422)
    # 2. Delegate to ImportService.preview()
    # 3. Return CsvPreviewResponse

@router.post("/imports/csv/confirm", response_model=CsvConfirmResponse, status_code=201)
async def confirm_import(body: CsvConfirmRequest, db: AsyncSession = Depends(get_db)):
    # 1. Delegate to ImportService.confirm()
    # 2. Return CsvConfirmResponse
```

File size is enforced at the endpoint level by reading `await file.read(MAX_SIZE + 1)` and checking length before passing bytes to the service.

### CSV Parser / Validator (`csv_parser.py`)

Pure function — takes raw bytes and two lookup dicts, returns structured results. No I/O.

```python
@dataclass
class ParsedRow:
    row_number: int          # 1-based
    province_id: UUID
    indicator_id: UUID
    value: Decimal
    reference_year: int
    dataset_name: str        # required — always present
    source_name: str | None  # required only when dataset_name is new
    source_url: str | None

@dataclass
class RowError:
    row_number: int
    column: str
    raw_value: str
    message: str

@dataclass
class ParseResult:
    valid_rows: list[ParsedRow]
    errors: list[RowError]
    duplicate_indices: list[int]   # row_number of duplicate occurrences

def parse_and_validate(
    raw_bytes: bytes,
    province_map: dict[str, UUID],      # code.upper() → province.id
    indicator_map: dict[str, UUID],     # code.upper() → indicator.id
    existing_dataset_names: set[str],   # names of Datasets already in DB
) -> ParseResult: ...
```

`dataset_name` is validated as non-empty on every row.
`source_name` is validated as non-empty only when the row's `dataset_name` is not in `existing_dataset_names` (i.e. it would create a new Dataset).

### Import Service (`import_service.py`)

```python
class ImportService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._repo = ImportRepository(session)

    async def preview(self, raw_bytes: bytes) -> CsvPreviewResponse:
        # 1. Load province_map, indicator_map, existing_dataset_names from DB
        # 2. Call parse_and_validate(raw_bytes, province_map, indicator_map, existing_dataset_names)
        # 3. Check for DB conflicts on valid, non-duplicate rows
        # 4. Store validated row set in TOKEN_STORE[token] with expiry
        # 5. Build and return CsvPreviewResponse (errors[:100], errors_truncated, total_error_count)

    async def confirm(self, preview_token: str) -> CsvConfirmResponse:
        # 1. Retrieve token from TOKEN_STORE; raise 404 if missing/expired
        # 2. Raise 422 if invalid_rows > 0 or duplicate_rows > 0
        # 3. Raise 409 with conflict list if conflict_rows > 0
        # 4. async with self._session.begin():   ← owns the transaction boundary
        #       a. get_or_create_dataset(dataset_name, source_name, source_url)
        #       b. bulk_insert_data_points(dataset_id, rows)
        #    Any exception inside the block rolls back automatically
        # 5. Invalidate token
        # 6. Return CsvConfirmResponse
```

### Import Repository (`import_repository.py`)

```python
class ImportRepository:
    async def load_province_map(self) -> dict[str, UUID]:
        # SELECT id, code FROM provinces → {code.upper(): id}

    async def load_indicator_map(self) -> dict[str, UUID]:
        # SELECT id, code FROM indicators → {code.upper(): id}

    async def load_dataset_names(self) -> set[str]:
        # SELECT name FROM datasets → set of existing dataset names (used to
        # determine whether source_name is required for a given CSV row)

    async def check_conflicts(
        self,
        dataset_id: UUID | None,
        rows: list[ParsedRow],
    ) -> list[NaturalKey]:
        # SELECT ... WHERE (indicator_id, province_id, reference_year, dataset_id) IN (...)
        # Returns list of conflicting natural keys

    async def get_or_create_dataset(
        self,
        dataset_name: str,
        source_name: str | None,
        source_url: str | None,
    ) -> Dataset:
        # SELECT by name; INSERT if not found
        # Does NOT commit — caller owns transaction via async with session.begin()

    async def bulk_insert_data_points(
        self,
        dataset_id: UUID,
        rows: list[ParsedRow],
    ) -> int:
        # session.add_all([DataPoint(...) for row in rows])
        # await session.flush()   ← does NOT commit; caller's async with session.begin() commits
        # Returns count
```

**Transaction ownership rule:** `ImportService.confirm` owns the transaction via `async with session.begin()`. Repository methods use only `session.add_all`, `session.flush`, and `session.execute` — they never call `session.commit()` or `session.rollback()`. This guarantees that any exception in any repository method causes the outer context manager to roll back the entire unit of work.

### Token Store

```python
# import_service.py module level
import asyncio, uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

TOKEN_TTL = timedelta(minutes=15)

@dataclass
class _TokenEntry:
    payload: CachedPreview
    expires_at: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc) + TOKEN_TTL
    )

_TOKEN_STORE: dict[str, _TokenEntry] = {}

def _store_token(payload: CachedPreview) -> str:
    token = str(uuid.uuid4())
    _TOKEN_STORE[token] = _TokenEntry(payload=payload)
    return token

def _retrieve_token(token: str) -> CachedPreview | None:
    entry = _TOKEN_STORE.get(token)
    if entry is None or datetime.now(timezone.utc) > entry.expires_at:
        _TOKEN_STORE.pop(token, None)
        return None
    return entry.payload

def _invalidate_token(token: str) -> None:
    _TOKEN_STORE.pop(token, None)
```

In-process dict is used for single-worker MVP deployments (`uvicorn … --workers 1`). This is a documented deployment constraint (REQ-13.7). Redis migration path: replace `_TOKEN_STORE` with a Redis client behind the same three helper functions, with no changes to `ImportService`.

---

## Pydantic Schemas (`schemas/imports.py`)

```python
class RowErrorSchema(BaseModel):
    row_number: int
    column: str
    raw_value: str
    message: str

class SampleRecordSchema(BaseModel):
    row_number: int
    province_code: str
    indicator_code: str
    value: Decimal
    reference_year: int
    dataset_name: str

class CsvPreviewResponse(BaseModel):
    preview_token: str
    total_rows: int
    valid_rows: int
    invalid_rows: int
    duplicate_rows: int
    conflict_rows: int
    can_confirm: bool
    errors: list[RowErrorSchema]              # max 100 items
    total_error_count: int                    # true total, may exceed 100
    errors_truncated: bool                    # true when total_error_count > 100
    sample_records: list[SampleRecordSchema]  # max 10 items

class CsvConfirmRequest(BaseModel):
    preview_token: str

class CsvConfirmResponse(BaseModel):
    imported_count: int
    dataset_id: uuid.UUID
```

---

## Frontend Architecture

### Page State Machine

```
IDLE  ──upload──►  UPLOADING  ──success──►  PREVIEWING  ──confirm──►  CONFIRMING  ──success──►  SUCCESS
                       │                         │                          │
                  error/413/415            error/422               error/409/422
                       │                         │                          │
                    IDLE                     PREVIEWING                PREVIEWING
                  (reset)                  (show errors)            (show conflict msg)
```

### `ImportPage.jsx`

Single page component — owns all state, delegates rendering to sub-components.

```jsx
const [state, setState]             = useState('idle')    // idle|uploading|previewing|confirming|success
const [previewData, setPreviewData] = useState(null)
const [importResult, setImportResult] = useState(null)
const [apiError, setApiError]       = useState(null)

async function handleUpload(file) { ... }
async function handleConfirm() { ... }
function handleReset() { setState('idle'); setPreviewData(null); setApiError(null) }
```

### `DropZone.jsx`

```jsx
// Props: onFile(File), disabled, maxSizeMB
// Client-side checks: extension === '.csv', size <= maxSizeMB * 1024 * 1024
// Drag events: dragenter, dragover, dragleave, drop
// Accessible: role="region", aria-label, visible focus, keyboard-activatable
```

### `api.js` additions

```js
export async function importPreview(file) {
  const form = new FormData()
  form.append('file', file)
  const res = await axios.post('/api/v1/imports/csv/preview', form, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
  return res.data
}

export async function importConfirm(previewToken) {
  const res = await axios.post('/api/v1/imports/csv/confirm', {
    preview_token: previewToken,
  })
  return res.data
}
```

---

## Data Flow — Preview

```
Browser                   FastAPI                    csv_parser          DB
  │                           │                           │               │
  │──POST /preview (file)────►│                           │               │
  │                           │── read bytes (≤5MB) ─────►│               │
  │                           │── load province_map ─────────────────────►│
  │                           │── load indicator_map ────────────────────►│
  │                           │── parse_and_validate ────►│               │
  │                           │◄─ ParseResult ────────────│               │
  │                           │── check_conflicts ───────────────────────►│
  │                           │◄─ conflict list ─────────────────────────│
  │                           │── store token in memory                   │
  │◄─ CsvPreviewResponse ─────│                                           │
```

## Data Flow — Confirm

```
Browser                   FastAPI                    DB (transaction)
  │                           │                           │
  │──POST /confirm (token)───►│                           │
  │                           │── retrieve token          │
  │                           │── BEGIN ─────────────────►│
  │                           │── get_or_create_dataset ─►│
  │                           │── bulk_insert_data_points►│
  │                           │── COMMIT ─────────────────│
  │                           │── invalidate token        │
  │◄─ CsvConfirmResponse ─────│                           │
```

---

## Error Handling

| Condition | HTTP status | Body |
|---|---|---|
| Wrong file type | 415 | `{"detail": "Only .csv files are accepted"}` |
| File > 5 MB | 413 | `{"detail": "File exceeds 5 MB limit"}` |
| Empty file | 422 | `{"detail": "Uploaded file is empty"}` |
| Too many rows (> 10,000) | 422 | `{"detail": "File exceeds 10,000 row limit"}` |
| Missing required columns | 422 | `{"detail": "Missing columns: [...]"}` |
| Row-level errors | 200 | `CsvPreviewResponse` with `can_confirm: false` |
| Unknown/expired token | 404 | `{"detail": "Preview token not found or expired"}` |
| Confirm with invalid rows | 422 | `{"detail": "Preview contains validation errors"}` |
| Confirm with duplicates | 422 | `{"detail": "Preview contains duplicate rows"}` |
| Confirm with conflicts | 409 | `{"detail": "Conflicts with existing data", "conflicts": [...]}` |
| DB error during insert | 500 | `{"detail": "Import failed — transaction rolled back"}` |

---

## Natural Key and Conflict Logic

The unique constraint in `data_points` is:
`(dataset_id, indicator_id, province_id, reference_year)` where `province_id IS NOT NULL`.

`dataset_name` is required in every CSV row. During preview the service looks up the Dataset by name:

- **Matching Dataset found** → use its `id` for the conflict check batch query:
  ```sql
  SELECT indicator_id, province_id, reference_year
  FROM data_points
  WHERE dataset_id = :dataset_id
    AND province_id IS NOT NULL
    AND (indicator_id, province_id, reference_year) = ANY(:tuples)
  ```
- **No matching Dataset** → no existing DataPoints can conflict (the Dataset doesn't exist yet); conflict check is skipped. `source_name` is required in this case (REQ-2.7).

On confirm, `get_or_create_dataset` either retrieves the existing Dataset or creates a new one (with `source_name`, `source_url`) within the `async with session.begin()` block before inserting DataPoints.

---

## Correctness Properties

1. **No partial import**: `ImportService.confirm` wraps all DB operations in `async with session.begin()`. SQLAlchemy's async context manager automatically rolls back on any exception and commits only on clean exit. Repository methods never call `commit()` or `rollback()` directly.

2. **Token immutability**: The token payload stored at preview time is never modified. The confirm endpoint reads the payload read-only and then deletes the token. It cannot re-validate against a stale CSV.

3. **Idempotent confirm**: Once a token is invalidated it cannot be reused. Retrying confirm with the same token returns 404.

4. **Pure parser**: `parse_and_validate` takes only bytes, two dicts, and a set of existing dataset names. It has no side effects and is independently unit-testable without a database.

5. **Hard-block on conflicts**: No force/overwrite path exists. Any row whose natural key already exists in the DB causes the confirm endpoint to return HTTP 409 and make zero inserts.

6. **Error cap with transparency**: The `errors` array is capped at 100 items. `total_error_count` always reflects the true count and `errors_truncated` signals when the list is partial, so the frontend can show the truncation notice.

---

## Test Strategy

### Backend (pytest + httpx AsyncClient)

| Test | File | Approach |
|---|---|---|
| Valid CSV → preview counts | `test_imports.py` | Upload 3-row valid CSV; assert `valid_rows=3, can_confirm=true` |
| Malformed CSV (binary) | `test_imports.py` | Upload PNG bytes; assert HTTP 415 |
| Missing columns | `test_imports.py` | Upload CSV missing `value`; assert HTTP 422 |
| Unknown province_code | `test_imports.py` | Row with `province_code=XX`; assert error in response |
| Non-numeric value | `test_imports.py` | Row with `value=abc`; assert error |
| Out-of-range year | `test_imports.py` | Row with `reference_year=1800`; assert error |
| Intra-file duplicate | `test_imports.py` | Two rows same natural key; assert `duplicate_rows=1` |
| DB conflict | `test_imports.py` | Pre-insert a DataPoint; assert `conflict_rows=1` |
| Confirm with conflict | `test_imports.py` | Token with conflict; assert HTTP 409 |
| Confirm success | `test_imports.py` | Full round-trip; assert HTTP 201 + DB row count |
| Transaction rollback | `test_imports.py` | Inject DB error mid-insert; assert 0 rows in DB |
| File too large | `test_imports.py` | 5 MB + 1 byte; assert HTTP 413 |
| Pure parser unit tests | `test_csv_parser.py` | Call `parse_and_validate` directly; no DB |
| Error list truncation | `test_imports.py` | Upload CSV with 110 invalid rows; assert `errors_truncated=true`, `len(errors)=100`, `total_error_count=110` |

### Frontend (Vitest + Testing Library)

| Test | File | Approach |
|---|---|---|
| Client-side size reject | `ImportPage.test.jsx` | Simulate 6 MB file; assert error without network call |
| Preview summary counts | `ImportPage.test.jsx` | Mock `importPreview`; assert count badges |
| Confirm button disabled | `ImportPage.test.jsx` | `can_confirm: false`; assert button disabled |
| Success state | `ImportPage.test.jsx` | Mock confirm; assert imported_count displayed |
| API error shown | `ImportPage.test.jsx` | Mock 422; assert error message |
| Truncation notice shown | `ImportPage.test.jsx` | Mock preview with `errors_truncated=true, total_error_count=150`; assert "Showing the first 100 of 150 validation errors." |

---

## Deployment Constraint

The application must run with a single Uvicorn worker for this MVP (`uvicorn app.main:app --workers 1`). The in-process `_TOKEN_STORE` is not shared across worker processes. This must be documented in the deployment README. The Redis upgrade path requires only replacing the three `_store_token` / `_retrieve_token` / `_invalidate_token` helper functions.
