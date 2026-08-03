"""
services/mapping_execution_service.py
======================================
Mapping execution service for StatFlow column mapping (Task 8B).

Responsibilities:
-----------------
1. Retrieve the inspection session by token.
2. Verify token ownership and expiry.
3. Validate a MappingConfiguration against business rules.
4. Resolve source values from a CSV row (column or fixed-value).
5. Apply individual transformations (pure ops synchronously;
   DB-backed ops via _apply_transformation_async).

Single-worker limitation
-------------------------
The inspection token store (_INSPECTION_STORE) is an in-process dict.
Tokens do not survive process restarts and are not shared across workers.

Do not call session.commit() or session.rollback() from this service.
"""

from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime as _datetime
from decimal import Decimal, InvalidOperation

from app.schemas.ingestion_mapping import (
    ColumnMapping,
    MappingConfiguration,
    MappingSourceType,
    TargetField,
    TransformationOperation,
)
from app.services.file_inspection_service import (
    CachedInspection,
    InspectionTokenExpiredError,
    InspectionTokenForbiddenError,
    InspectionTokenNotFoundError,
    _retrieve_inspection_token,
)
from app.services.mapped_preview_service import (
    CachedMappedPreview,
    _store_mapped_preview_token,
)
from sqlalchemy.ext.asyncio import AsyncSession

SUPPORTED_MAPPING_VERSION = 1

_REQUIRED_TARGETS = {
    TargetField.PROVINCE_CODE,
    TargetField.INDICATOR_CODE,
    TargetField.VALUE,
    TargetField.REFERENCE_YEAR,
    TargetField.DATASET_NAME,
}

# ---------------------------------------------------------------------------
# Domain exceptions
# ---------------------------------------------------------------------------


class MappingExecutionError(Exception):
    """Base class for mapping execution errors."""


class InspectionNotFoundError(MappingExecutionError):
    """Token does not exist or has expired."""


class InspectionOwnershipError(MappingExecutionError):
    """Token belongs to a different user."""


class InvalidMappingError(MappingExecutionError):
    def __init__(self, errors: list[str]) -> None:
        self.errors = errors
        super().__init__("; ".join(errors))


class SourceColumnNotFoundError(MappingExecutionError):
    def __init__(self, column_name: str, target_field: str) -> None:
        self.column_name = column_name
        self.target_field = target_field
        super().__init__(
            f"Source column '{column_name}' not found in the uploaded file "
            f"(required for target field '{target_field}')."
        )


class UnsupportedTransformationError(MappingExecutionError):
    def __init__(self, operation: str) -> None:
        self.operation = operation
        super().__init__(
            f"Transformation operation '{operation}' is not supported in this version."
        )


class TransformationExecutionError(MappingExecutionError):
    def __init__(self, operation: str, raw_value: str, reason: str) -> None:
        self.operation = operation
        self.raw_value = raw_value
        self.reason = reason
        super().__init__(f"Transformation '{operation}' failed on value {raw_value!r}: {reason}")


# ---------------------------------------------------------------------------
# Preview result
# ---------------------------------------------------------------------------


@dataclass
class MappingPreviewResult:
    """
    Returned by MappingExecutionService.generate_mapping_preview().

    Attributes
    ----------
    transformed_rows : list[dict[str, object]]
        Each dict maps target_field names to transformed values.
        One entry per sample row extracted from the inspection session.
    total_preview_rows : int
        Number of sample rows that were processed (== len(transformed_rows)).
    mapped_column_count : int
        Number of ColumnMappings in the applied configuration.
    original_headers : list[str]
        The source CSV headers stored in the inspection session.
    target_fields : list[str]
        The canonical target field names produced by the mapping
        (e.g. ["province_code", "indicator_code", ...]).
    """

    transformed_rows: list[dict[str, object]] = field(default_factory=list)
    total_preview_rows: int = 0
    mapped_column_count: int = 0
    original_headers: list[str] = field(default_factory=list)
    target_fields: list[str] = field(default_factory=list)
    mapped_preview_token: str | None = None


# ---------------------------------------------------------------------------
# extract_year helper (module-level, pure/sync)
# ---------------------------------------------------------------------------

_YEAR_MIN = 1900
_YEAR_MAX = 2100

_DATE_FORMATS = [
    "%Y-%m-%dT%H:%M:%SZ",
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%d",
    "%Y/%m/%d",
    "%d-%m-%Y",
    "%d/%m/%Y",
    "%m-%d-%Y",
    "%m/%d/%Y",
]


def _validate_year_range(year: int, raw: str) -> int:
    if year < _YEAR_MIN or year > _YEAR_MAX:
        raise TransformationExecutionError(
            "extract_year",
            raw,
            f"Year {year} is outside the allowed range [{_YEAR_MIN}, {_YEAR_MAX}].",
        )
    return year


def _extract_year(value: object) -> int:
    if value is None:
        return None  # type: ignore[return-value]
    if isinstance(value, bool):
        raise TransformationExecutionError(
            "extract_year", str(value), "Boolean values cannot be used as a year."
        )
    if isinstance(value, int):
        return _validate_year_range(value, str(value))
    if isinstance(value, (float, Decimal)):
        raise TransformationExecutionError(
            "extract_year",
            str(value),
            "Float and Decimal values are not accepted; provide a string date or integer year.",
        )
    if isinstance(value, str):
        cleaned = value.strip()
        if not cleaned:
            raise TransformationExecutionError(
                "extract_year", value, "Cannot extract a year from an empty string."
            )
        if re.fullmatch(r"\d{4}", cleaned):
            return _validate_year_range(int(cleaned), value)
        for fmt in _DATE_FORMATS:
            try:
                dt = _datetime.strptime(cleaned, fmt)
                return _validate_year_range(dt.year, value)
            except ValueError:
                continue
        raise TransformationExecutionError(
            "extract_year",
            value,
            f"Could not extract a year from {cleaned!r}. "
            "Expected a 4-digit year or a recognisable date string.",
        )
    raise TransformationExecutionError(
        "extract_year",
        str(value),
        f"Cannot extract a year from a value of type {type(value).__name__}.",
    )


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class MappingExecutionService:
    """
    Orchestrates column-mapping execution against a previously inspected file.
    Stateless per-request; DB session injected for async (DB-backed) operations.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    # ------------------------------------------------------------------
    # Inspection retrieval
    # ------------------------------------------------------------------

    def get_inspection(self, inspection_token: str, owner_id: uuid.UUID) -> CachedInspection:
        try:
            return _retrieve_inspection_token(inspection_token, owner_id)
        except InspectionTokenExpiredError as exc:
            raise InspectionNotFoundError(
                "Inspection token has expired. Upload the file again."
            ) from exc
        except InspectionTokenNotFoundError as exc:
            raise InspectionNotFoundError(
                "Inspection token not found. It may have expired or never existed."
            ) from exc
        except InspectionTokenForbiddenError as exc:
            raise InspectionOwnershipError(
                "Inspection token does not belong to the current user."
            ) from exc

    # ------------------------------------------------------------------
    # Source-value resolution
    # ------------------------------------------------------------------

    @staticmethod
    def _resolve_source_value(
        mapping: ColumnMapping,
        source_row: dict[str, str],
    ) -> str:
        if mapping.source_type == MappingSourceType.COLUMN:
            col = mapping.source_column or ""
            if col not in source_row:
                raise SourceColumnNotFoundError(
                    column_name=col, target_field=mapping.target_field.value
                )
            return source_row[col]
        return mapping.fixed_value or ""

    # ------------------------------------------------------------------
    # Pure (synchronous) transformations
    # ------------------------------------------------------------------

    @staticmethod
    def _apply_transformation(operation: TransformationOperation, value: object) -> object:
        """
        Apply a single pure (non-DB) transformation.

        province_name_to_code requires DB access and is NOT handled here —
        call _apply_transformation_async() for that operation.
        """
        if operation == TransformationOperation.TRIM:
            return value.strip() if isinstance(value, str) else value

        if operation == TransformationOperation.UPPERCASE:
            return value.upper() if isinstance(value, str) else value

        if operation == TransformationOperation.LOWERCASE:
            return value.lower() if isinstance(value, str) else value

        if operation == TransformationOperation.PARSE_NUMBER:
            if value is None or isinstance(value, bool):
                return value
            if isinstance(value, (int, float, Decimal)):
                return value
            if isinstance(value, str):
                cleaned = value.strip().replace(",", "")
                if not cleaned:
                    raise TransformationExecutionError(
                        "parse_number", value, "Cannot parse an empty string as a number."
                    )
                try:
                    d = Decimal(cleaned)
                    if not d.is_finite():
                        raise TransformationExecutionError(
                            "parse_number",
                            value,
                            f"Result is not a finite number: {cleaned!r}.",
                        )
                    return d
                except InvalidOperation:
                    raise TransformationExecutionError(
                        "parse_number",
                        value,
                        f"Cannot convert {cleaned!r} to a number.",
                    )
            return value

        if operation == TransformationOperation.EXTRACT_YEAR:
            return _extract_year(value)

        if operation == TransformationOperation.PROVINCE_NAME_TO_CODE:
            err = UnsupportedTransformationError(operation.value)
            err.args = (
                "province_name_to_code requires a database session; "
                "call _apply_transformation_async() instead.",
            )
            raise err

        raise UnsupportedTransformationError(operation.value)

    # ------------------------------------------------------------------
    # Async transformations (DB-backed)
    # ------------------------------------------------------------------

    async def _apply_transformation_async(
        self,
        operation: TransformationOperation,
        value: object,
    ) -> object:
        """
        Apply a single transformation, including DB-backed operations.

        Delegates to _apply_transformation for all pure ops; handles
        province_name_to_code via _province_name_to_code().
        """
        if operation == TransformationOperation.PROVINCE_NAME_TO_CODE:
            return await self._province_name_to_code(value)
        return self._apply_transformation(operation, value)

    async def _province_name_to_code(self, value: object) -> str:
        """
        Resolve a province name to its canonical code via the database.

        Case-insensitive, whitespace-tolerant lookup against Province.name.
        Returns the province code string (e.g. "LK" for "Lusaka").
        """
        from app.models.province import Province
        from sqlalchemy import func, select

        if value is None:
            return None  # type: ignore[return-value]

        if isinstance(value, bool) or not isinstance(value, str):
            raise TransformationExecutionError(
                "province_name_to_code",
                str(value),
                f"Expected a province name string, got {type(value).__name__}.",
            )

        cleaned = value.strip()
        if not cleaned:
            raise TransformationExecutionError(
                "province_name_to_code", value, "Cannot look up an empty province name."
            )

        stmt = select(Province).where(func.lower(func.trim(Province.name)) == cleaned.lower())
        result = await self._session.execute(stmt)
        rows = result.scalars().all()

        if not rows:
            raise TransformationExecutionError(
                "province_name_to_code",
                value,
                f"Unknown province name: {cleaned!r}. "
                "Check the spelling or use the canonical province code directly.",
            )

        if len(rows) > 1:
            codes = [r.code for r in rows]
            raise TransformationExecutionError(
                "province_name_to_code",
                value,
                f"Ambiguous province name {cleaned!r} matched multiple records: {codes}.",
            )

        return rows[0].code

    # ------------------------------------------------------------------
    # Row execution
    # ------------------------------------------------------------------

    async def _execute_row(
        self,
        mapping_configuration: MappingConfiguration,
        source_row: dict[str, str],
    ) -> dict[str, object]:
        """
        Apply the full mapping configuration to a single source row.

        For each ColumnMapping in ``mapping_configuration.mappings``:
          1. Resolve the raw source value via ``_resolve_source_value``.
          2. Apply all configured transformations via ``_apply_transformations``.
          3. Store the result in the target dict keyed by ``target_field.value``.

        Parameters
        ----------
        mapping_configuration
            The validated MappingConfiguration to apply.
        source_row
            A dict representing one CSV row, keyed by header name.

        Returns
        -------
        dict[str, object]
            Target field name → transformed value.  Keys are always the
            canonical target field name strings (e.g. ``"province_code"``).

        Raises
        ------
        SourceColumnNotFoundError
            If a column-source mapping references a column not in source_row.
        TransformationExecutionError
            If a transformation fails at runtime.
        UnsupportedTransformationError
            If a transformation operation is not implemented.
        """
        result: dict[str, object] = {}
        for mapping in mapping_configuration.mappings:
            raw = self._resolve_source_value(mapping, source_row)
            transformed = await self._apply_transformations(mapping, raw)
            result[mapping.target_field.value] = transformed
        return result

    async def _execute_rows(
        self,
        mapping_configuration: MappingConfiguration,
        source_rows: list[dict[str, str]],
    ) -> list[dict[str, object]]:
        """
        Apply the mapping configuration to every row in *source_rows*.

        Rows are processed in their original order.  Each row is passed to
        ``_execute_row``; the resulting target dicts are collected in order.

        Parameters
        ----------
        mapping_configuration
            The validated MappingConfiguration to apply to every row.
        source_rows
            An ordered list of source-row dicts.  This list and its contents
            are never mutated.

        Returns
        -------
        list[dict[str, object]]
            One target dict per source row, in the same order as source_rows.
            Returns an empty list when source_rows is empty.

        Raises
        ------
        SourceColumnNotFoundError, TransformationExecutionError,
        UnsupportedTransformationError
            Propagated immediately from the failing row; processing stops.
            The original exception is not wrapped.
        """
        results: list[dict[str, object]] = []
        for row in source_rows:
            results.append(await self._execute_row(mapping_configuration, row))
        return results

    # ------------------------------------------------------------------
    # Transformation chaining
    # ------------------------------------------------------------------

    async def _apply_transformations(
        self,
        mapping: ColumnMapping,
        raw_value: object,
    ) -> object:
        """
        Apply the full transformation chain declared on *mapping* to *raw_value*.

        Transformations are applied left-to-right in the exact order listed in
        ``mapping.transformations``.  Each operation receives the output of the
        previous one as its input.

        Parameters
        ----------
        mapping
            The ColumnMapping whose ``.transformations`` list defines the chain.
        raw_value
            The initial value (from a CSV cell or a fixed-value literal).

        Returns
        -------
        object
            The value after all transformations have been applied.
            If ``mapping.transformations`` is empty, *raw_value* is returned
            unchanged.  ``None`` passes through unless a transformation
            explicitly converts it.

        Raises
        ------
        TransformationExecutionError
            Propagated immediately when any operation in the chain fails.
            The chain stops at the first error.
        UnsupportedTransformationError
            Propagated immediately when an operation is not implemented.
        """
        value = raw_value
        for rule in mapping.transformations:
            value = await self._apply_transformation_async(rule.operation, value)
        return value

    # ------------------------------------------------------------------
    # Public API — generate mapping preview
    # ------------------------------------------------------------------

    @staticmethod
    def _build_sample_rows(inspection: "CachedInspection") -> list[dict[str, str]]:
        """
        Reconstruct row dicts from the column-oriented sample_values stored in
        the CachedInspection.

        Each column stores up to 10 sample values independently.  Row ``i``
        gets ``column.sample_values[i]`` when available, or ``""`` otherwise.
        The maximum number of rows is the length of the longest column's
        sample_values list.

        Parameters
        ----------
        inspection
            The cached inspection payload returned by get_inspection().

        Returns
        -------
        list[dict[str, str]]
            Zero or more row dicts keyed by the original header name.
        """
        if not inspection.columns:
            return []

        max_len = max((len(col.sample_values) for col in inspection.columns), default=0)
        if max_len == 0:
            return []

        rows: list[dict[str, str]] = []
        for i in range(max_len):
            row: dict[str, str] = {}
            for col in inspection.columns:
                row[col.name] = col.sample_values[i] if i < len(col.sample_values) else ""
            rows.append(row)
        return rows

    async def generate_mapping_preview(
        self,
        inspection_token: str,
        owner_id: uuid.UUID,
        mapping_configuration: MappingConfiguration,
    ) -> MappingPreviewResult:
        """
        Apply a mapping configuration to the sample rows from an inspection
        session and return a preview of the transformed data.

        Steps
        -----
        1. Validate the mapping configuration (validate_mapping).
        2. Retrieve the inspection session (get_inspection).
        3. Reconstruct sample rows from the column sample_values.
        4. Execute mappings against those rows (_execute_rows).
        5. Return a MappingPreviewResult.

        Parameters
        ----------
        inspection_token
            Token returned by POST /imports/files/inspect.
        owner_id
            UUID of the authenticated user — must match the token owner.
        mapping_configuration
            The MappingConfiguration to preview.  Validated before use.

        Returns
        -------
        MappingPreviewResult

        Raises
        ------
        InvalidMappingError
            If the mapping configuration fails validation.
        InspectionNotFoundError
            If the token is missing or expired.
        InspectionOwnershipError
            If the token belongs to a different user.
        SourceColumnNotFoundError, TransformationExecutionError,
        UnsupportedTransformationError
            Propagated directly from row execution without wrapping.
        """
        # Step 1 — validate mapping (raises InvalidMappingError on failure)
        self.validate_mapping(mapping_configuration)

        # Step 2 — retrieve inspection (raises InspectionNotFoundError /
        #           InspectionOwnershipError on failure)
        inspection = self.get_inspection(inspection_token, owner_id)

        # Step 3 — reconstruct sample rows from column sample_values
        sample_rows = self._build_sample_rows(inspection)

        # Step 4 — execute (empty rows list returns [] immediately)
        transformed_rows = await self._execute_rows(mapping_configuration, sample_rows)

        # Step 5 — assemble result
        target_fields = [m.target_field.value for m in mapping_configuration.mappings]

        # Store a short-lived mapped-preview token so the frontend can confirm
        # the previewed mapping before creating persistent datasets.
        payload = CachedMappedPreview(
            mapped_preview_token="",
            transformed_rows=transformed_rows,
            mapping_configuration=mapping_configuration,
            source_filename=inspection.filename,
            original_headers=list(inspection.headers),
            owner_id=owner_id,
        )
        mapped_token = _store_mapped_preview_token(payload)
        # Replace the stored payload with one that contains the token value.
        payload = CachedMappedPreview(
            mapped_preview_token=mapped_token,
            transformed_rows=transformed_rows,
            mapping_configuration=mapping_configuration,
            source_filename=inspection.filename,
            original_headers=list(inspection.headers),
            owner_id=owner_id,
        )
        # overwrite store entry so payload includes token
        from app.services.mapped_preview_service import _MAPPED_PREVIEW_STORE, _MappedPreviewEntry

        _MAPPED_PREVIEW_STORE[mapped_token] = _MappedPreviewEntry(payload=payload)

        return MappingPreviewResult(
            transformed_rows=transformed_rows,
            total_preview_rows=len(transformed_rows),
            mapped_column_count=len(mapping_configuration.mappings),
            original_headers=list(inspection.headers),
            target_fields=target_fields,
            mapped_preview_token=mapped_token,
        )

    # ------------------------------------------------------------------
    # Mapping validation
    # ------------------------------------------------------------------

    def validate_mapping(self, mapping_config: MappingConfiguration) -> MappingConfiguration:
        """
        Validate a MappingConfiguration against StatFlow business rules.

        Rules:
          1. mapping_version == 1
          2. All five required target fields present
          3. No duplicate target fields
          4. Each mapping has exactly one source (column XOR fixed_value)
          5. All transformation operations are in the whitelisted enum

        Returns the same object on success; raises InvalidMappingError otherwise.
        """
        errors: list[str] = []

        if mapping_config.mapping_version != SUPPORTED_MAPPING_VERSION:
            errors.append(
                f"mapping_version must be {SUPPORTED_MAPPING_VERSION}; "
                f"got {mapping_config.mapping_version}."
            )

        seen_targets: dict[TargetField, int] = {}
        for idx, m in enumerate(mapping_config.mappings):
            if m.target_field in seen_targets:
                errors.append(
                    f"Duplicate target field '{m.target_field.value}' "
                    f"at mapping index {idx} (also at index {seen_targets[m.target_field]})."
                )
            else:
                seen_targets[m.target_field] = idx

        missing = _REQUIRED_TARGETS - seen_targets.keys()
        if missing:
            errors.append(f"Missing required target field(s): {sorted(t.value for t in missing)}.")

        for idx, m in enumerate(mapping_config.mappings):
            if m.source_type == MappingSourceType.COLUMN:
                if not m.source_column:
                    errors.append(
                        f"Mapping {idx} (target '{m.target_field.value}'): "
                        "source_type is 'column' but source_column is empty."
                    )
                if m.fixed_value:
                    errors.append(
                        f"Mapping {idx} (target '{m.target_field.value}'): "
                        "source_type is 'column' but fixed_value is also set."
                    )
            elif m.source_type == MappingSourceType.FIXED_VALUE:
                if not m.fixed_value:
                    errors.append(
                        f"Mapping {idx} (target '{m.target_field.value}'): "
                        "source_type is 'fixed_value' but fixed_value is empty."
                    )
                if m.source_column:
                    errors.append(
                        f"Mapping {idx} (target '{m.target_field.value}'): "
                        "source_type is 'fixed_value' but source_column is also set."
                    )

        valid_ops = {op.value for op in TransformationOperation}
        for idx, m in enumerate(mapping_config.mappings):
            for t_idx, t in enumerate(m.transformations):
                if t.operation.value not in valid_ops:
                    errors.append(
                        f"Mapping {idx} (target '{m.target_field.value}'), "
                        f"transformation {t_idx}: unsupported operation '{t.operation.value}'."
                    )

        if errors:
            raise InvalidMappingError(errors)

        return mapping_config
