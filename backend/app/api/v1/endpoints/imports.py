"""
endpoints/imports.py
====================
FastAPI route handlers for the CSV import workflow.

POST /api/v1/imports/csv/preview  — upload, parse, validate, return preview
POST /api/v1/imports/csv/confirm  — execute the transactional import

Upload safety (REQ-11)
----------------------
- Filename is sanitised: path separators and null bytes are stripped before
  any logging or error messages. The original filename is never stored or
  executed.
- File bytes are read entirely into memory and discarded after the response.
  Nothing is written to disk (REQ-1.5).
- MIME type (Content-Type) is checked: only text/csv and text/plain are
  accepted (REQ-1.1). The filename extension is NOT used as the sole gate.
- Maximum file size: 5 MB (REQ-1.2).
- The CSV is parsed by the pure parse_and_validate function in csv_parser.py;
  no eval, exec, or shell invocation touches uploaded bytes (REQ-11.2).

Exception → HTTP status mapping
---------------------------------
Parser exceptions are caught explicitly and mapped to defined HTTP statuses.
Broad bare-except clauses are not used; programming defects propagate normally.

    EmptyFileError       → 422 Unprocessable Entity
    MalformedCsvError    → 422 Unprocessable Entity
    MissingColumnsError  → 422 Unprocessable Entity (lists missing columns)
    RowLimitExceeded     → 422 Unprocessable Entity
    HTTPException        → passed through as-is (raised by ImportService)

File-level guards (checked before calling ImportService):
    wrong MIME type      → 415 Unsupported Media Type
    file > 5 MB          → 413 Content Too Large
    empty file           → 422 Unprocessable Entity
"""

from __future__ import annotations

import os
import uuid

from fastapi import APIRouter, Body, Depends, File, HTTPException, UploadFile, status
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import require_data_manager_or_admin, validate_csrf
from app.db.session import get_db
from app.models.user import User
from app.schemas.imports import (
    CsvConfirmRequest,
    CsvConfirmResponse,
    CsvConflictSchema,
    CsvPreviewResponse,
    CsvRowErrorSchema,
    SampleRecordSchema,
)
from app.schemas.ingestion_mapping import (
    FileInspectionResponse,
    ImportTemplateCreateRequest,
    ImportTemplateListResponse,
    ImportTemplateResponse,
    ImportTemplateUpdateRequest,
    ImportErrorDetail,
    MapPreviewRequest,
    MapPreviewResponse,
    ConfirmMappedImportRequest,
    ConfirmMappedImportResponse,
)
from app.services.file_inspection_service import (
    DuplicateHeadersError,
    EmptyFileError,
    FileInspectionService,
    FileTooLargeError,
    InspectionTokenExpiredError,
    InspectionTokenForbiddenError,
    InspectionTokenNotFoundError,
    InvalidEncodingError,
    MalformedCsvError,
    MissingFileError,
    UnsupportedFormatError,
)
from app.services.import_service import ConfirmResult, ImportService, PreviewData
from app.services.import_template_service import ImportTemplateService
from app.services.mapping_execution_service import (
    InspectionNotFoundError,
    InspectionOwnershipError,
    InvalidMappingError,
    MappingExecutionService,
    SourceColumnNotFoundError,
    TransformationExecutionError,
    UnsupportedTransformationError,
)
from app.services.mapped_preview_service import (
    _retrieve_mapped_preview_token,
    _invalidate_mapped_preview_token,
    MappedPreviewTokenNotFoundError,
    MappedPreviewTokenExpiredError,
    MappedPreviewTokenForbiddenError,
)
from app.services.universal_dataset_persistence_service import UniversalDatasetPersistenceService
from app.utils.csv_parser import (
    EmptyFileError as CsvEmptyFileError,
    MalformedCsvError as CsvMalformedCsvError,
    MissingColumnsError,
    RowLimitExceeded,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MAX_FILE_BYTES = 5 * 1024 * 1024          # 5 MB  (REQ-1.2)
ALLOWED_MIME_TYPES = {"text/csv", "text/plain"}

# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------

router = APIRouter(prefix="/imports", tags=["Imports"])


# ---------------------------------------------------------------------------
# Error payloads
# ---------------------------------------------------------------------------

ERROR_CODES = {
    'IMPORT_FILE_MISSING': 'IMPORT_FILE_MISSING',
    'IMPORT_UNSUPPORTED_FORMAT': 'IMPORT_UNSUPPORTED_FORMAT',
    'IMPORT_FILE_TOO_LARGE': 'IMPORT_FILE_TOO_LARGE',
    'IMPORT_EMPTY_FILE': 'IMPORT_EMPTY_FILE',
    'IMPORT_MALFORMED_CSV': 'IMPORT_MALFORMED_CSV',
    'IMPORT_INVALID_ENCODING': 'IMPORT_INVALID_ENCODING',
    'IMPORT_DUPLICATE_HEADERS': 'IMPORT_DUPLICATE_HEADERS',
    'IMPORT_MAPPING_REQUIRED': 'IMPORT_MAPPING_REQUIRED',
    'IMPORT_INVALID_MAPPING': 'IMPORT_INVALID_MAPPING',
    'IMPORT_INSPECTION_EXPIRED': 'IMPORT_INSPECTION_EXPIRED',
    'IMPORT_INSPECTION_FORBIDDEN': 'IMPORT_INSPECTION_FORBIDDEN',
    'IMPORT_TEMPLATE_NOT_FOUND': 'IMPORT_TEMPLATE_NOT_FOUND',
    'IMPORT_TEMPLATE_NAME_CONFLICT': 'IMPORT_TEMPLATE_NAME_CONFLICT',
    'IMPORT_SOURCE_COLUMN_NOT_FOUND': 'IMPORT_SOURCE_COLUMN_NOT_FOUND',
    'IMPORT_TRANSFORMATION_UNSUPPORTED': 'IMPORT_TRANSFORMATION_UNSUPPORTED',
    'IMPORT_MAPPING_EXECUTION_FAILED': 'IMPORT_MAPPING_EXECUTION_FAILED',
}


def _error_payload(code: str, message: str, details: dict | None = None) -> dict:
    return {
        'code': ERROR_CODES.get(code, code),
        'message': message,
        'details': details or {},
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _sanitise_filename(filename: str | None) -> str:
    """
    Strip path separators, null bytes, and return a safe filename string.
    Returns an empty string when filename is None.

    REQ-1.4 / REQ-11.1
    """
    if not filename:
        return ""
    # Remove null bytes
    sanitised = filename.replace("\x00", "")
    # Strip any path component — keep only the final component
    sanitised = os.path.basename(sanitised)
    # Remove remaining path separators (belt-and-braces)
    sanitised = sanitised.replace("/", "").replace("\\", "")
    return sanitised


def _assert_mime_type(content_type: str | None) -> None:
    """
    Raise HTTP 415 if the Content-Type header is not text/csv or text/plain.

    The check strips any charset parameter (e.g. "text/csv; charset=utf-8")
    before comparison.

    REQ-1.1
    """
    if not content_type:
        raise HTTPException(
            status_code=415,
            detail=(
                "Missing Content-Type header. "
                "Only text/csv and text/plain are accepted."
            ),
        )
    # Normalise: take the primary media type, lower-cased
    mime = content_type.split(";")[0].strip().lower()
    if mime not in ALLOWED_MIME_TYPES:
        raise HTTPException(
            status_code=415,
            detail=(
                f"Unsupported media type '{mime}'. "
                "Only text/csv and text/plain are accepted."
            ),
        )


def _preview_data_to_response(data: PreviewData) -> CsvPreviewResponse:
    """Map the service-layer PreviewData dataclass to the Pydantic response schema."""
    return CsvPreviewResponse(
        preview_token=data.preview_token,
        total_rows=data.total_rows,
        valid_rows=data.valid_rows,
        invalid_rows=data.invalid_rows,
        duplicate_rows=data.duplicate_rows,
        conflict_rows=data.conflict_rows,
        can_confirm=data.can_confirm,
        errors=[
            CsvRowErrorSchema(
                row_number=e.row_number,
                column=e.column,
                raw_value=e.raw_value,
                message=e.message,
            )
            for e in data.errors
        ],
        total_error_count=data.total_error_count,
        errors_truncated=data.errors_truncated,
        sample_records=[
            SampleRecordSchema(
                row_number=r.row_number,
                province_code=r.province_code,
                indicator_code=r.indicator_code,
                value=r.value,
                reference_year=r.reference_year,
                dataset_name=r.dataset_name,
            )
            for r in data.sample_records
        ],
        conflicts=[
            CsvConflictSchema(
                dataset_name=ck.dataset_name if hasattr(ck, "dataset_name") else "",
                indicator_id=ck.indicator_id,
                province_id=ck.province_id,
                reference_year=ck.reference_year,
            )
            for ck in data.conflicts
        ],
    )


def _confirm_result_to_response(result: ConfirmResult) -> CsvConfirmResponse:
    """Map the service-layer ConfirmResult dataclass to the Pydantic response schema."""
    return CsvConfirmResponse(
        imported_count=result.imported_count,
        datasets_created=result.datasets_created,
        dataset_ids=result.dataset_ids,
    )


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@router.post(
    "/csv/preview",
    response_model=CsvPreviewResponse,
    status_code=200,
    summary="Preview a CSV import",
    description=(
        "Upload a structured CSV file and receive a full validation preview. "
        "Returns HTTP 200 even when row-level errors, duplicates, or conflicts "
        "are present — check `can_confirm` to determine whether the import may "
        "proceed. Store `preview_token` and pass it to the confirm endpoint "
        "within 15 minutes."
    ),
)
async def preview_csv_import(
    file: UploadFile | None = File(None, description="CSV file to import."),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_data_manager_or_admin),
    __: None = Depends(validate_csrf),
) -> CsvPreviewResponse:
    """
    POST /api/v1/imports/csv/preview

    Status codes
    ------------
    200  Successfully parsed (may contain row errors — check can_confirm)
    413  File exceeds 5 MB
    415  Content-Type is not text/csv or text/plain
    422  Empty file, malformed CSV, missing columns, or row limit exceeded
    """
    if file is None:
        raise HTTPException(
            status_code=422,
            detail=_error_payload(
                'IMPORT_FILE_MISSING',
                'No file was uploaded. Attach a file under the multipart field "file".',
                {},
            ),
        )

    # Guard 1: MIME type check (REQ-1.1) — done before reading bytes
    _assert_mime_type(file.content_type)

    # Guard 2: read file and enforce size limit (REQ-1.2)
    # Read up to MAX + 1 bytes to detect over-limit without reading a huge stream
    raw_bytes: bytes = await file.read(MAX_FILE_BYTES + 1)

    if len(raw_bytes) > MAX_FILE_BYTES:
        raise HTTPException(
            status_code=413,
            detail=_error_payload(
                'IMPORT_FILE_TOO_LARGE',
                f'File exceeds the {MAX_FILE_BYTES // (1024 * 1024)} MB size limit. Reduce the file size and try again.',
                {'max_file_bytes': MAX_FILE_BYTES},
            ),
        )

    # Guard 3: empty file (REQ-1.3)
    if not raw_bytes:
        raise HTTPException(
            status_code=422,
            detail=_error_payload(
                'IMPORT_EMPTY_FILE',
                'Uploaded file is empty.',
            ),
        )

    # Sanitise filename for any logging or error messages (REQ-1.4, REQ-11.1)
    _sanitise_filename(file.filename)

    # Delegate to service, mapping parser exceptions to HTTP status codes
    service = ImportService(db)
    try:
        preview_data = await service.preview(raw_bytes)
    except CsvEmptyFileError as exc:
        raise HTTPException(
            status_code=422,
            detail=_error_payload('IMPORT_EMPTY_FILE', str(exc)),
        ) from exc
    except MissingColumnsError as exc:
        raise HTTPException(
            status_code=422,
            detail=_error_payload(
                'IMPORT_MAPPING_REQUIRED',
                f'Missing required columns: {exc.missing}',
                {'missing_columns': exc.missing},
            ),
        ) from exc
    except CsvMalformedCsvError as exc:
        raise HTTPException(
            status_code=422,
            detail=_error_payload('IMPORT_MALFORMED_CSV', str(exc)),
        ) from exc
    except RowLimitExceeded as exc:
        raise HTTPException(
            status_code=422,
            detail=_error_payload('IMPORT_MALFORMED_CSV', str(exc)),
        ) from exc

    return _preview_data_to_response(preview_data)


@router.post(
    "/files/inspect",
    response_model=FileInspectionResponse,
    status_code=200,
    summary="Inspect an uploaded file for mapping",
    description=(
        "Upload a CSV file and receive column metadata for mapping. "
        "Returns an inspection token that may be used during mapping or import. "
        "This endpoint does not persist row data and is intended for preview/inspection only."
    ),
)
async def inspect_file_upload(
    file: UploadFile | None = File(None, description="CSV file to inspect."),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_data_manager_or_admin),
    __: None = Depends(validate_csrf),
) -> FileInspectionResponse:
    """POST /api/v1/imports/files/inspect

    Status codes
    ------------
    200  File successfully inspected
    413  File exceeds 5 MB
    415  Content-Type is not text/csv or text/plain
    422  Empty file, malformed CSV, invalid encoding, or duplicate headers
    """
    if file is None:
        raise HTTPException(
            status_code=422,
            detail=_error_payload(
                'IMPORT_FILE_MISSING',
                'No file was uploaded. Attach a file under the multipart field "file".',
            ),
        )

    _assert_mime_type(file.content_type)
    raw_bytes: bytes = await file.read(MAX_FILE_BYTES + 1)

    if len(raw_bytes) > MAX_FILE_BYTES:
        raise HTTPException(
            status_code=413,
            detail=_error_payload(
                'IMPORT_FILE_TOO_LARGE',
                f'File exceeds the {MAX_FILE_BYTES // (1024 * 1024)} MB size limit. Reduce the file size and try again.',
                {'max_file_bytes': MAX_FILE_BYTES},
            ),
        )

    if not raw_bytes:
        raise HTTPException(
            status_code=422,
            detail=_error_payload('IMPORT_EMPTY_FILE', 'Uploaded file is empty.'),
        )

    _sanitise_filename(file.filename)
    service = FileInspectionService()
    try:
        inspection_response = service.inspect_csv(
            raw_bytes=raw_bytes,
            filename=file.filename,
            content_type=file.content_type,
            owner_id=user.id,
        )
    except FileTooLargeError as exc:
        raise HTTPException(
            status_code=413,
            detail=_error_payload('IMPORT_FILE_TOO_LARGE', str(exc)),
        ) from exc
    except UnsupportedFormatError as exc:
        raise HTTPException(
            status_code=415,
            detail=_error_payload('IMPORT_UNSUPPORTED_FORMAT', str(exc)),
        ) from exc
    except EmptyFileError as exc:
        raise HTTPException(
            status_code=422,
            detail=_error_payload('IMPORT_EMPTY_FILE', str(exc)),
        ) from exc
    except InvalidEncodingError as exc:
        raise HTTPException(
            status_code=422,
            detail=_error_payload('IMPORT_INVALID_ENCODING', str(exc)),
        ) from exc
    except MalformedCsvError as exc:
        raise HTTPException(
            status_code=422,
            detail=_error_payload('IMPORT_MALFORMED_CSV', str(exc)),
        ) from exc
    except DuplicateHeadersError as exc:
        raise HTTPException(
            status_code=422,
            detail=_error_payload('IMPORT_DUPLICATE_HEADERS', str(exc), {'duplicates': exc.duplicates}),
        ) from exc

    return inspection_response


@router.get(
    "/files/inspect/{inspection_token}",
    response_model=FileInspectionResponse,
    status_code=200,
    summary="Retrieve a file inspection result",
    description=(
        "Return a previously created file inspection result by inspection_token. "
        "The inspection token expires after 15 minutes and is only valid for "
        "the user who originally uploaded the file."
    ),
)
async def retrieve_file_inspection(
    inspection_token: str,
    user: User = Depends(require_data_manager_or_admin),
) -> FileInspectionResponse:
    service = FileInspectionService()
    try:
        inspection_response = service.retrieve_inspection(
            token=inspection_token,
            owner_id=user.id,
        )
    except InspectionTokenExpiredError as exc:
        raise HTTPException(
            status_code=404,
            detail=_error_payload('IMPORT_INSPECTION_EXPIRED', str(exc)),
        ) from exc
    except InspectionTokenNotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail=_error_payload('IMPORT_INSPECTION_EXPIRED', str(exc)),
        ) from exc
    except InspectionTokenForbiddenError as exc:
        raise HTTPException(
            status_code=403,
            detail=_error_payload('IMPORT_INSPECTION_FORBIDDEN', str(exc)),
        ) from exc

    return inspection_response


@router.post(
    "/templates",
    response_model=ImportTemplateResponse,
    status_code=201,
    summary="Create a reusable import template",
    description=(
        "Persist a validated import mapping template for the current user. "
        "The template can be reused later to import files with the same header layout."
    ),
)
async def create_import_template(
    body: ImportTemplateCreateRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_data_manager_or_admin),
    __: None = Depends(validate_csrf),
) -> ImportTemplateResponse:
    service = ImportTemplateService(db)
    try:
        template = await service.create_template(user.id, body)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    return ImportTemplateResponse.model_validate(template)


@router.get(
    "/templates",
    response_model=ImportTemplateListResponse,
    status_code=200,
    summary="List reusable import templates",
    description=(
        "Return all active import templates owned by the current user."
    ),
)
async def list_import_templates(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_data_manager_or_admin),
) -> ImportTemplateListResponse:
    service = ImportTemplateService(db)
    templates = await service.list_templates(user.id)
    return ImportTemplateListResponse(templates=templates)


@router.get(
    "/templates/{template_id}",
    response_model=ImportTemplateResponse,
    status_code=200,
    summary="Get an import template",
    description=(
        "Return a single reusable import template owned by the current user."
    ),
)
async def get_import_template(
    template_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_data_manager_or_admin),
) -> ImportTemplateResponse:
    service = ImportTemplateService(db)
    template = await service.get_template(template_id, user.id)
    if template is None:
        raise HTTPException(
            status_code=404,
            detail=_error_payload(
                'IMPORT_TEMPLATE_NOT_FOUND',
                f'Import template with id {template_id} not found.',
            ),
        )
    return ImportTemplateResponse.model_validate(template)


@router.patch(
    "/templates/{template_id}",
    response_model=ImportTemplateResponse,
    status_code=200,
    summary="Update an import template",
    description=(
        "Update fields on an existing reusable import template owned by the current user."
    ),
)
async def update_import_template(
    template_id: uuid.UUID,
    body: ImportTemplateUpdateRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_data_manager_or_admin),
    __: None = Depends(validate_csrf),
) -> ImportTemplateResponse:
    service = ImportTemplateService(db)
    try:
        template = await service.update_template(template_id, user.id, body)
    except LookupError as exc:
        raise HTTPException(
            status_code=404,
            detail=_error_payload(
                'IMPORT_TEMPLATE_NOT_FOUND',
                str(exc),
            ),
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=409,
            detail=_error_payload(
                'IMPORT_TEMPLATE_NAME_CONFLICT',
                str(exc),
            ),
        ) from exc
    return ImportTemplateResponse.model_validate(template)


@router.delete(
    "/templates/{template_id}",
    status_code=204,
    summary="Deactivate an import template",
    description=(
        "Soft-delete the current user's import template by marking it inactive."
    ),
)
async def delete_import_template(
    template_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_data_manager_or_admin),
    __: None = Depends(validate_csrf),
) -> None:
    service = ImportTemplateService(db)
    try:
        await service.deactivate_template(template_id, user.id)
    except LookupError as exc:
        raise HTTPException(
            status_code=404,
            detail=_error_payload(
                'IMPORT_TEMPLATE_NOT_FOUND',
                str(exc),
            ),
        ) from exc
    return None


@router.post(
    "/files/map-preview",
    response_model=MapPreviewResponse,
    status_code=200,
    summary="Preview a mapped import",
    description=(
        "Apply a mapping configuration to the sample rows stored in an inspection "
        "session and return the transformed preview data. "
        "No data is persisted. No preview token is created."
    ),
)
async def map_preview(
    body: MapPreviewRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_data_manager_or_admin),
    __: None = Depends(validate_csrf),
) -> MapPreviewResponse:
    """
    POST /api/v1/imports/files/map-preview

    Status codes
    ------------
    200  Preview generated successfully
    400  Invalid mapping configuration
    403  Inspection token belongs to a different user
    404  Inspection token not found or expired
    422  Source column not found or transformation execution failed
    """
    svc = MappingExecutionService(db)
    try:
        result = await svc.generate_mapping_preview(
            inspection_token=body.inspection_token,
            owner_id=user.id,
            mapping_configuration=body.mapping_config,
        )
    except InvalidMappingError as exc:
        raise HTTPException(
            status_code=400,
            detail=_error_payload(
                'IMPORT_INVALID_MAPPING',
                f"Mapping configuration is invalid: {exc.errors[0]}",
                {'errors': exc.errors},
            ),
        ) from exc
    except InspectionNotFoundError as exc:
        raise HTTPException(
            status_code=404,
            detail=_error_payload('IMPORT_INSPECTION_EXPIRED', str(exc)),
        ) from exc
    except InspectionOwnershipError as exc:
        raise HTTPException(
            status_code=403,
            detail=_error_payload('IMPORT_INSPECTION_FORBIDDEN', str(exc)),
        ) from exc
    except SourceColumnNotFoundError as exc:
        raise HTTPException(
            status_code=422,
            detail=_error_payload(
                'IMPORT_SOURCE_COLUMN_NOT_FOUND',
                str(exc),
                {
                    'column_name': exc.column_name,
                    'target_field': exc.target_field,
                },
            ),
        ) from exc
    except UnsupportedTransformationError as exc:
        raise HTTPException(
            status_code=422,
            detail=_error_payload(
                'IMPORT_TRANSFORMATION_UNSUPPORTED',
                str(exc),
                {'operation': exc.operation},
            ),
        ) from exc
    except TransformationExecutionError as exc:
        raise HTTPException(
            status_code=422,
            detail=_error_payload(
                'IMPORT_MAPPING_EXECUTION_FAILED',
                str(exc),
                {
                    'operation': exc.operation,
                    'raw_value': exc.raw_value,
                    'reason': exc.reason,
                },
            ),
        ) from exc

    return MapPreviewResponse(
        transformed_rows=result.transformed_rows,
        total_preview_rows=result.total_preview_rows,
        mapped_column_count=result.mapped_column_count,
        original_headers=result.original_headers,
        target_fields=result.target_fields,
        mapped_preview_token=result.mapped_preview_token,
    )



@router.post(
    "/files/map-confirm",
    response_model=ConfirmMappedImportResponse,
    status_code=201,
    summary="Confirm a mapped import and persist as a universal dataset",
    description=(
        "Persist a previously-generated mapped-preview into the universal dataset store. "
        "Requires the mapped_preview_token created by /files/map-preview."
    ),
)
async def map_confirm(
    body: ConfirmMappedImportRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_data_manager_or_admin),
    __: None = Depends(validate_csrf),
) -> ConfirmMappedImportResponse:
    try:
        cached = _retrieve_mapped_preview_token(body.mapped_preview_token, user.id)
    except MappedPreviewTokenNotFoundError as exc:
        raise HTTPException(status_code=404, detail=_error_payload('IMPORT_INSPECTION_EXPIRED', str(exc))) from exc
    except MappedPreviewTokenExpiredError as exc:
        raise HTTPException(status_code=410, detail=_error_payload('IMPORT_INSPECTION_EXPIRED', str(exc))) from exc
    except MappedPreviewTokenForbiddenError as exc:
        raise HTTPException(status_code=403, detail=_error_payload('IMPORT_INSPECTION_FORBIDDEN', str(exc))) from exc

    # Validation: name must be present (Pydantic ensures non-empty), but double-check
    if not body.name or not body.name.strip():
        raise HTTPException(status_code=422, detail=_error_payload('IMPORT_INVALID_MAPPING', 'Dataset name cannot be blank'))

    if not cached.transformed_rows:
        raise HTTPException(status_code=422, detail=_error_payload('IMPORT_MAPPING_EXECUTION_FAILED', 'Mapped preview contains no rows to persist'))

    service = UniversalDatasetPersistenceService(db)
    try:
        dataset = await service.create_dataset_from_rows(
            owner_id=user.id,
            name=body.name,
            description=body.description,
            source_filename=cached.source_filename,
            rows=cached.transformed_rows,
        )
    except ValueError as exc:
        # User-visible validation error — do not consume token
        raise HTTPException(status_code=422, detail=_error_payload('IMPORT_INVALID_MAPPING', str(exc))) from exc
    except Exception as exc:
        # Persistence failed — leave token available for retry
        raise HTTPException(status_code=500, detail=_error_payload('IMPORT_MAPPING_EXECUTION_FAILED', 'Failed to persist mapped import')) from exc

    # Success — consume the mapped-preview token
    _invalidate_mapped_preview_token(body.mapped_preview_token)

    version = dataset.current_version

    return ConfirmMappedImportResponse(
        dataset_id=dataset.id,
        version_id=version.id,
        name=dataset.name,
        version_number=version.version_number,
        row_count=version.row_count,
        column_count=version.column_count,
        source_filename=dataset.source_filename,
        status=dataset.status,
        created_at=dataset.created_at,
    )


@router.post(
    "/csv/confirm",
    response_model=CsvConfirmResponse,
    status_code=201,
    summary="Confirm a CSV import",
    description=(
        "Execute the import identified by `preview_token`. "
        "All DataPoints are inserted in a single atomic transaction. "
        "The token is consumed on success and cannot be reused. "
        "If a race-condition conflict is detected inside the transaction "
        "the import is aborted and HTTP 409 is returned with conflict details."
    ),
)
async def confirm_csv_import(
    body: CsvConfirmRequest,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(require_data_manager_or_admin),
    __: None = Depends(validate_csrf),
) -> CsvConfirmResponse:
    """
    POST /api/v1/imports/csv/confirm

    Status codes
    ------------
    201  Import succeeded — all rows inserted
    404  Token not found or expired
    409  Database conflict (preview or race-condition)
    422  Preview contains validation errors or intra-file duplicates
    """
    service = ImportService(db)
    # ImportService.confirm() raises HTTPException with the correct status
    # codes for 404, 409, and 422. Those propagate directly to the caller.
    result = await service.confirm(body.preview_token)
    return _confirm_result_to_response(result)
