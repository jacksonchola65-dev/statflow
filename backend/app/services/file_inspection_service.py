"""
services/file_inspection_service.py
===================================
File inspection service for uploaded CSV files.

This service is intentionally lightweight and deterministic. It reads file
bytes safely, enforces size limits, and returns column metadata without
persisting any data.
"""

from __future__ import annotations

import csv
import io
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from typing import Any

from app.schemas.ingestion_mapping import (
    ColumnMapping,
    FileInspectionResponse,
    MappingSourceType,
    SourceColumn,
    SourceColumnType,
    TargetField,
)
from app.semantic.analytics_role_service import AnalyticsRoleService
from app.semantic.detection_pipeline import SemanticDetectionPipeline
from app.semantic.detectors.base import DetectorInput
from app.semantic.detectors.dictionary_detector import DictionarySemanticDetector
from app.semantic.detectors.regex_detector import RegexSemanticDetector
from app.semantic.detectors.value_sampling_detector import ValueSamplingDetector
from app.semantic.dimension_detector import DimensionColumnInput, DimensionDetector
from app.semantic.entity_candidate_detector import EntityCandidateDetector, EntityColumnInput
from app.semantic.entity_key_detector import (
    EntityKeyColumnInput,
    EntityKeyDetectionInput,
    EntityKeyDetector,
)
from app.semantic.measure_detector import MeasureColumnInput, MeasureDetector
from app.semantic.relationship_detector import (
    RelationshipColumnInput,
    RelationshipDetectionInput,
    RelationshipDetector,
)
from app.semantic.semantic_profile_builder import (
    ColumnClassification,
    DomainDetectionResult,
    SemanticProfileBuilder,
)
from app.semantic.semantic_serialization import to_dict as semantic_to_dict
from app.semantic.semantic_types import DatasetDomain
from app.semantic.v2.integration import (
    compose_semantic_profile_from_columns,
    get_semantic_engine_version,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

TOKEN_TTL = timedelta(minutes=15)
MAX_FILE_BYTES = 5 * 1024 * 1024
MAX_SAMPLE_ROWS = 10
MAX_COLUMN_NAME_LENGTH = 200
MAX_COLUMNS = 200
MAX_SAMPLE_VALUES = 10
MAX_SAMPLE_VALUE_LENGTH = 300
ALLOWED_EXTENSIONS = {"csv", "txt"}
ALLOWED_MIME_TYPES = {"text/csv", "text/plain"}
CANONICAL_REQUIRED_HEADERS = {
    "province_code",
    "indicator_code",
    "value",
    "reference_year",
    "dataset_name",
}

# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class InspectionError(Exception):
    pass


class FileTooLargeError(InspectionError):
    pass


class EmptyFileError(InspectionError):
    pass


class MalformedCsvError(InspectionError):
    pass


class UnsupportedFormatError(InspectionError):
    pass


class DuplicateHeadersError(InspectionError):
    def __init__(self, duplicates: list[str]) -> None:
        self.duplicates = duplicates
        super().__init__(f"Duplicate headers detected: {duplicates}")


class InvalidEncodingError(InspectionError):
    pass


class MissingFileError(InspectionError):
    pass


class InspectionTokenNotFoundError(InspectionError):
    pass


class InspectionTokenExpiredError(InspectionError):
    pass


class InspectionTokenForbiddenError(InspectionError):
    pass


# ---------------------------------------------------------------------------
# Inspection token store
# ---------------------------------------------------------------------------


@dataclass
class _InspectionTokenEntry:
    payload: "CachedInspection"
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


_INSPECTION_STORE: dict[str, _InspectionTokenEntry] = {}


def _store_inspection_token(payload: "CachedInspection") -> str:
    token = str(uuid.uuid4())
    _INSPECTION_STORE[token] = _InspectionTokenEntry(payload=payload)
    return token


def _retrieve_inspection_token(token: str, user_id: uuid.UUID) -> "CachedInspection":
    entry = _INSPECTION_STORE.get(token)
    if entry is None:
        raise InspectionTokenNotFoundError("Inspection token not found.")
    if datetime.now(timezone.utc) > entry.created_at + TOKEN_TTL:
        _INSPECTION_STORE.pop(token, None)
        raise InspectionTokenExpiredError("Inspection token expired.")
    if entry.payload.owner_id != user_id:
        raise InspectionTokenForbiddenError("Inspection token does not belong to this user.")
    return entry.payload


def _invalidate_inspection_token(token: str) -> None:
    _INSPECTION_STORE.pop(token, None)


# ---------------------------------------------------------------------------
# Internal objects
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CachedInspection:
    inspection_token: str
    filename: str
    source_format: str
    headers: list[str]
    columns: list[SourceColumn]
    direct_schema_match: bool
    suggested_mappings: list[Any]
    warnings: list[str]
    owner_id: uuid.UUID


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------


def _validate_extension(filename: str) -> None:
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext not in ALLOWED_EXTENSIONS:
        raise UnsupportedFormatError(
            f"Unsupported file extension '.{ext}'. Only .csv and .txt files are accepted."
        )


def _normalize_filename(filename: str | None) -> str:
    if not filename:
        return ""
    filename = filename.replace("\x00", "")
    return filename.rsplit("/", 1)[-1].rsplit("\\", 1)[-1]


def _validate_mime_type(content_type: str | None) -> None:
    if not content_type:
        raise UnsupportedFormatError("Missing Content-Type header.")
    mime = content_type.split(";", 1)[0].strip().lower()
    if mime not in ALLOWED_MIME_TYPES:
        raise UnsupportedFormatError(
            f"Unsupported media type '{mime}'. Only text/csv and text/plain are accepted."
        )


def _decode_bytes(raw_bytes: bytes) -> str:
    if not raw_bytes:
        raise EmptyFileError("Uploaded file is empty.")
    if len(raw_bytes) > MAX_FILE_BYTES:
        raise FileTooLargeError(
            f"File exceeds the {MAX_FILE_BYTES // (1024 * 1024)} MB size limit."
        )
    try:
        text = raw_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise InvalidEncodingError(f"File could not be decoded as UTF-8: {exc}") from exc
    if text.startswith("\ufeff"):
        text = text[len("\ufeff") :]
    return text


def _detect_dialect(text: str) -> csv.Dialect:
    sample = text[:4096]
    try:
        return csv.Sniffer().sniff(sample, delimiters=",;\t|")
    except csv.Error:
        return csv.excel  # type: ignore[return-value]


def _normalize_header(header: str) -> str:
    return header.strip().lower()


def _build_suggested_mappings(
    headers: list[str],
    normalized_headers: list[str],
) -> list[ColumnMapping]:
    suggestions: list[ColumnMapping] = []
    normalized_to_header = {_normalize_header(header): header.strip() for header in headers}
    mapping_targets = [
        TargetField.PROVINCE_CODE,
        TargetField.INDICATOR_CODE,
        TargetField.VALUE,
        TargetField.REFERENCE_YEAR,
        TargetField.DATASET_NAME,
    ]
    for target in mapping_targets:
        normalized_target = target.value
        if normalized_target in normalized_to_header:
            suggestions.append(
                ColumnMapping(
                    target_field=target,
                    source_type=MappingSourceType.COLUMN,
                    source_column=normalized_to_header[normalized_target],
                    transformations=[],
                    required=True,
                )
            )
    return suggestions


def _infer_value_type(value: str) -> SourceColumnType:
    if value == "":
        return SourceColumnType.EMPTY

    normalized = value.strip()
    if normalized == "":
        return SourceColumnType.EMPTY

    if _is_boolean(normalized):
        return SourceColumnType.BOOLEAN
    if _is_integer(normalized):
        return SourceColumnType.INTEGER
    if _is_decimal(normalized):
        return SourceColumnType.DECIMAL
    if _is_date(normalized):
        return SourceColumnType.DATE
    return SourceColumnType.STRING


def _is_boolean(value: str) -> bool:
    return value.lower() in {"true", "false", "yes", "no", "1", "0"}


def _is_integer(value: str) -> bool:
    return bool(re.fullmatch(r"[+-]?\d+", value))


def _is_decimal(value: str) -> bool:
    try:
        dec = Decimal(value)
    except InvalidOperation:
        return False
    return dec.is_finite()


def _is_date(value: str) -> bool:
    iso_match = re.fullmatch(r"\d{4}-\d{2}-\d{2}", value)
    if iso_match:
        try:
            datetime.fromisoformat(value)
            return True
        except ValueError:
            return False

    for fmt in ("%Y/%m/%d", "%m/%d/%Y", "%d/%m/%Y", "%Y%m%d"):
        try:
            datetime.strptime(value, fmt)
            return True
        except ValueError:
            continue
    return False


def _infer_column_type(values: list[str]) -> SourceColumnType:
    non_empty_values = [v for v in values if v != ""]
    if not non_empty_values:
        return SourceColumnType.EMPTY

    inferred_types = [_infer_value_type(v) for v in non_empty_values]
    types = {t for t in inferred_types if t != SourceColumnType.EMPTY}

    if len(types) == 1:
        return types.pop()

    if types <= {SourceColumnType.INTEGER, SourceColumnType.DECIMAL}:
        return SourceColumnType.DECIMAL

    if types <= {SourceColumnType.STRING, SourceColumnType.INTEGER, SourceColumnType.DECIMAL}:
        return SourceColumnType.STRING

    return SourceColumnType.MIXED


def _collect_samples(rows: list[list[str]], max_samples: int) -> list[str]:
    samples: list[str] = []
    for value in rows:
        if value != "" and len(samples) < max_samples:
            samples.append(value)
        if len(samples) >= max_samples:
            break
    return samples


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


class FileInspectionService:
    def inspect_csv(
        self,
        raw_bytes: bytes,
        filename: str | None,
        content_type: str | None,
        owner_id: uuid.UUID,
    ) -> FileInspectionResponse:
        """Inspect a CSV file and return structured header/column metadata."""
        filename = _normalize_filename(filename)
        _validate_extension(filename)
        _validate_mime_type(content_type)
        text = _decode_bytes(raw_bytes)

        dialect = _detect_dialect(text)
        try:
            reader = csv.reader(io.StringIO(text), dialect=dialect)
            headers = next(reader)
        except StopIteration:
            raise EmptyFileError("CSV file has no header row.")
        except csv.Error as exc:
            raise MalformedCsvError(f"CSV parsing failed: {exc}") from exc

        if len(headers) > MAX_COLUMNS:
            raise MalformedCsvError(
                f"CSV file contains too many columns ({len(headers)}). Maximum is {MAX_COLUMNS}."
            )

        normalized_headers = [_normalize_header(h) for h in headers]
        if any(len(h) == 0 for h in normalized_headers):
            raise MalformedCsvError("CSV header contains an empty column name.")
        if any(len(h) > MAX_COLUMN_NAME_LENGTH for h in headers):
            raise MalformedCsvError(
                f"CSV header names must be {MAX_COLUMN_NAME_LENGTH} characters or fewer."
            )

        duplicates = [h for h in set(normalized_headers) if normalized_headers.count(h) > 1]
        if duplicates:
            raise DuplicateHeadersError(sorted(duplicates))

        sample_rows: list[list[str]] = []
        row_count = 0
        for row in reader:
            if len(row) == 0:
                continue
            row_count += 1
            if len(sample_rows) < MAX_SAMPLE_ROWS:
                sample_rows.append(row)
            if row_count >= MAX_SAMPLE_ROWS:
                break

        columns: list[SourceColumn] = []
        num_columns = len(normalized_headers)
        column_samples: list[list[str]] = [[] for _ in range(num_columns)]
        nullable_flags = [False] * num_columns

        for row in sample_rows:
            normalized_row = [cell.strip() for cell in row]
            if len(normalized_row) < num_columns:
                normalized_row += [""] * (num_columns - len(normalized_row))
            for idx in range(num_columns):
                value = normalized_row[idx] if idx < len(normalized_row) else ""
                if value == "":
                    nullable_flags[idx] = True
                else:
                    column_samples[idx].append(value[:MAX_SAMPLE_VALUE_LENGTH])

        for idx, header in enumerate(headers):
            sample_values = _collect_samples(column_samples[idx], MAX_SAMPLE_VALUES)
            inferred_type = _infer_column_type([v for v in column_samples[idx]])
            columns.append(
                SourceColumn(
                    name=header.strip(),
                    inferred_type=inferred_type,
                    sample_values=sample_values,
                    nullable=nullable_flags[idx],
                    position=idx + 1,
                )
            )

        headers_list = [header.strip() for header in headers]
        direct_schema_match = CANONICAL_REQUIRED_HEADERS.issubset(
            {h.lower() for h in normalized_headers}
        )

        warnings: list[str] = []
        suggested_mappings = _build_suggested_mappings(headers_list, normalized_headers)

        payload = CachedInspection(
            inspection_token="",
            filename=filename,
            source_format="csv",
            headers=headers_list,
            columns=columns,
            direct_schema_match=direct_schema_match,
            suggested_mappings=suggested_mappings,
            warnings=warnings,
            owner_id=owner_id,
        )
        inspection_token = _store_inspection_token(payload)
        payload = CachedInspection(
            inspection_token=inspection_token,
            filename=filename,
            source_format="csv",
            headers=headers_list,
            columns=columns,
            direct_schema_match=direct_schema_match,
            suggested_mappings=suggested_mappings,
            warnings=warnings,
            owner_id=owner_id,
        )
        _INSPECTION_STORE[inspection_token] = _InspectionTokenEntry(payload=payload)
        # ------------------------------------------------------------------
        # Semantic detection integration (best-effort)
        # - Default is v2 native fused runtime; v1 remains available via SEMANTIC_ENGINE_VERSION=v1.
        # - If any semantic component is unavailable or raises, fall back to empty profile.
        # ------------------------------------------------------------------
        semantic_profile_dict = {}
        try:
            engine = get_semantic_engine_version()
        except Exception:
            engine = "v1"

        if engine != "v2":
            # v1 default path (unchanged behavior)
            try:
                detectors = [
                    ValueSamplingDetector(),
                    RegexSemanticDetector(),
                    DictionarySemanticDetector(),
                ]
                pipeline = SemanticDetectionPipeline(detectors)

                # build cleaned DetectorInput objects once for the whole batch
                detector_inputs: list[DetectorInput] = []
                for col in columns:
                    cleaned = []
                    for v in col.sample_values:
                        if v is None:
                            continue
                        s = v if isinstance(v, str) else str(v)
                        if s.strip() == "":
                            continue
                        cleaned.append(s)
                        if len(cleaned) >= 100:
                            break

                    detector_inputs.append(
                        DetectorInput(
                            column_name=col.name,
                            values=tuple(cleaned),
                            inferred_type=(
                                col.inferred_type.value
                                if hasattr(col.inferred_type, "value")
                                else str(col.inferred_type)
                            ),
                        )
                    )

                batch_classifications = pipeline.run_batch(detector_inputs)
                col_classifications = [
                    ColumnClassification(
                        column_name=col.name, classifications=tuple(classifications)
                    )
                    for col, classifications in zip(columns, batch_classifications)
                ]

                # build entity candidate inputs
                entity_inputs = tuple(
                    EntityColumnInput(column_name=c.column_name, classifications=c.classifications)
                    for c in col_classifications
                )
                entities = EntityCandidateDetector.discover(entity_inputs)

                # build key, relationship, and analytics role inputs using cached classifications
                ek_inputs = []
                rel_inputs = []
                measure_inputs = []
                dimension_inputs = []
                for sc in columns:
                    samples = sc.sample_values
                    sample_size = len(samples)
                    unique_ratio = (len(set(samples)) / sample_size) if sample_size > 0 else 0.0
                    null_ratio = 1.0 if sc.nullable else 0.0
                    cls = tuple(
                        next(
                            (
                                cc.classifications
                                for cc in col_classifications
                                if cc.column_name == sc.name
                            ),
                            (),
                        )
                    )
                    ek_inputs.append(
                        EntityKeyColumnInput(
                            column_name=sc.name,
                            classifications=cls,
                            uniqueness_ratio=unique_ratio,
                            null_ratio=null_ratio,
                        )
                    )
                    rel_inputs.append(
                        RelationshipColumnInput(
                            column_name=sc.name,
                            classifications=cls,
                            uniqueness_ratio=unique_ratio,
                            null_ratio=null_ratio,
                        )
                    )
                    measure_inputs.append(
                        MeasureColumnInput(
                            column_name=sc.name,
                            classifications=cls,
                            cardinality_ratio=unique_ratio,
                            null_ratio=null_ratio,
                        )
                    )
                    dimension_inputs.append(
                        DimensionColumnInput(
                            column_name=sc.name,
                            classifications=cls,
                            cardinality_ratio=unique_ratio,
                            null_ratio=null_ratio,
                        )
                    )

                keys = EntityKeyDetector.discover(
                    EntityKeyDetectionInput(entities=entities, columns=tuple(ek_inputs))
                )
                rels = RelationshipDetector.discover(
                    RelationshipDetectionInput(
                        entities=entities, keys=keys, columns=tuple(rel_inputs)
                    )
                )
                measures = MeasureDetector.discover(tuple(measure_inputs))
                dimensions = DimensionDetector.discover(tuple(dimension_inputs))
                analytics_roles = AnalyticsRoleService.compose(measures, dimensions)

                # Compose semantic profile
                domain_result = DomainDetectionResult(domain=DatasetDomain.GENERAL)
                profile = SemanticProfileBuilder.compose(
                    domain_result, entities, rels, keys, analytics_roles, tuple(col_classifications)
                )
                # serialize the composed profile directly
                semantic_profile_dict = semantic_to_dict(profile)
            except Exception:
                semantic_profile_dict = {}
        else:
            # v2 native fused path: use prebuilt ColumnFeatureContext and native pipeline
            try:
                semantic_profile_dict = compose_semantic_profile_from_columns(columns)
            except Exception:
                semantic_profile_dict = {}

        return FileInspectionResponse(
            inspection_token=inspection_token,
            filename=filename,
            source_format="csv",
            headers=headers_list,
            columns=columns,
            direct_schema_match=direct_schema_match,
            suggested_mappings=suggested_mappings,
            warnings=warnings,
            semantic_profile=semantic_profile_dict,
        )

    def retrieve_inspection(self, token: str, owner_id: uuid.UUID) -> FileInspectionResponse | None:
        cached = _retrieve_inspection_token(token, owner_id)
        if cached is None:
            return None
        return FileInspectionResponse(
            inspection_token=cached.inspection_token,
            filename=cached.filename,
            source_format=cached.source_format,
            headers=cached.headers,
            columns=cached.columns,
            direct_schema_match=cached.direct_schema_match,
            suggested_mappings=cached.suggested_mappings,
            warnings=cached.warnings,
        )
