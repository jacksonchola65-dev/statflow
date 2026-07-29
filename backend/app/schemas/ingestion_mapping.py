"""
schemas/ingestion_mapping.py
============================
Pydantic v2 domain models for flexible CSV import mapping.

These schemas define the canonical mapping configuration language for the
StatFlow data ingestion engine. They are designed to be:

- JSON serializable (stored in database JSONB)
- Deterministic and testable
- Validation-oriented (no arbitrary code execution)
- Version-aware (mapping_version field supports future migrations)

The mapping framework separates source inspection (SourceColumn) from
target field definitions (TargetField) and transformation operations.

All transformations are whitelisted; no arbitrary code is accepted.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime
from typing import Annotated, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------


class SourceColumnType(str, enum.Enum):
    """Inferred data types from CSV column inspection."""

    STRING = "string"
    INTEGER = "integer"
    DECIMAL = "decimal"
    DATE = "date"
    BOOLEAN = "boolean"
    EMPTY = "empty"  # All sampled values are blank
    MIXED = "mixed"  # Column contains values of multiple types


class TargetField(str, enum.Enum):
    """Required and optional fields in the StatFlow canonical schema."""

    PROVINCE_CODE = "province_code"
    INDICATOR_CODE = "indicator_code"
    VALUE = "value"
    REFERENCE_YEAR = "reference_year"
    DATASET_NAME = "dataset_name"
    SOURCE_NAME = "source_name"  # Optional


class MappingSourceType(str, enum.Enum):
    """Source of a target field value: from CSV column or fixed value."""

    COLUMN = "column"
    FIXED_VALUE = "fixed_value"


class TransformationOperation(str, enum.Enum):
    """Whitelisted transformation operations (no arbitrary code)."""

    TRIM = "trim"  # Remove leading/trailing whitespace
    UPPERCASE = "uppercase"  # Convert to uppercase
    LOWERCASE = "lowercase"  # Convert to lowercase
    PARSE_NUMBER = "parse_number"  # Parse string to decimal number
    EXTRACT_YEAR = "extract_year"  # Extract year from date-like string
    PROVINCE_NAME_TO_CODE = "province_name_to_code"  # Map province name to code


# ---------------------------------------------------------------------------
# Source inspection metadata
# ---------------------------------------------------------------------------


class SourceColumn(BaseModel):
    """Metadata about a column inferred during file inspection."""

    name: Annotated[str, Field(
        min_length=1,
        description="Column name (from CSV header).",
    )]
    inferred_type: Annotated[SourceColumnType, Field(
        description="Inferred data type based on sampling.",
    )]
    sample_values: Annotated[list[str], Field(
        description=(
            "Up to 10 sample non-empty values from this column. "
            "Empty if column is entirely empty."
        ),
    )]
    nullable: Annotated[bool, Field(
        description="True if any sampled row has a blank/empty cell.",
    )]
    position: Annotated[int, Field(
        ge=1,
        description="1-based column position in the CSV.",
    )]


# ---------------------------------------------------------------------------
# Transformation rules
# ---------------------------------------------------------------------------


class TransformationRule(BaseModel):
    """A single transformation operation applied to a mapped value."""

    operation: Annotated[TransformationOperation, Field(
        description="Whitelisted transformation to apply.",
    )]

    class Config:
        json_schema_extra = {
            "examples": [
                {"operation": "trim"},
                {"operation": "uppercase"},
                {"operation": "parse_number"},
            ]
        }


# ---------------------------------------------------------------------------
# Column mapping
# ---------------------------------------------------------------------------


class ColumnMapping(BaseModel):
    """Mapping from a source column (or fixed value) to a target field."""

    target_field: Annotated[TargetField, Field(
        description="Target StatFlow field.",
    )]
    source_type: Annotated[MappingSourceType, Field(
        description="Whether value comes from a CSV column or is fixed.",
    )]
    source_column: Annotated[Optional[str], Field(
        default=None,
        description="Name of source CSV column (required if source_type == 'column').",
    )]
    fixed_value: Annotated[Optional[str], Field(
        default=None,
        description="Fixed string value (required if source_type == 'fixed_value').",
    )]
    transformations: Annotated[list[TransformationRule], Field(
        default_factory=list,
        description="Transformations applied to the source value, in order.",
    )]
    required: Annotated[bool, Field(
        default=True,
        description=(
            "If True, validation fails if the source value is empty. "
            "Optional for source_name only."
        ),
    )]

    @model_validator(mode="after")
    def validate_exactly_one_source(self) -> "ColumnMapping":
        """Ensure exactly one of source_column or fixed_value is provided."""
        if self.source_type == MappingSourceType.COLUMN:
            if not self.source_column:
                raise ValueError(
                    "source_column is required when source_type is 'column'"
                )
            if self.fixed_value:
                raise ValueError(
                    "fixed_value must be None when source_type is 'column'"
                )
        elif self.source_type == MappingSourceType.FIXED_VALUE:
            if not self.fixed_value:
                raise ValueError(
                    "fixed_value is required when source_type is 'fixed_value'"
                )
            if self.source_column:
                raise ValueError(
                    "source_column must be None when source_type is 'fixed_value'"
                )
        return self

    @field_validator("transformations")
    @classmethod
    def validate_transformations(cls, v: list[TransformationRule]) -> list[TransformationRule]:
        """Validate transformation rules (all operations already whitelisted by enum)."""
        if len(v) > 10:
            raise ValueError("Maximum 10 transformations per mapping")
        return v


# ---------------------------------------------------------------------------
# Complete mapping configuration
# ---------------------------------------------------------------------------


class MappingConfiguration(BaseModel):
    """
    Complete mapping definition for a data import.

    Stored as JSONB in ImportTemplate.mapping_config.
    The mapping_version field supports future schema migrations.
    """

    mapping_version: Annotated[int, Field(
        ge=1,
        description=(
            "Version of the mapping schema. Support for future migrations. "
            "Currently always 1."
        ),
    )] = 1
    
    mappings: Annotated[list[ColumnMapping], Field(
        min_items=5,  # At least the 5 required fields
        description="List of column mappings.",
    )]

    @field_validator("mappings")
    @classmethod
    def validate_required_fields_mapped(cls, v: list[ColumnMapping]) -> list[ColumnMapping]:
        """Ensure all required target fields are mapped."""
        required_targets = {
            TargetField.PROVINCE_CODE,
            TargetField.INDICATOR_CODE,
            TargetField.VALUE,
            TargetField.REFERENCE_YEAR,
            TargetField.DATASET_NAME,
        }
        mapped_targets = {m.target_field for m in v}
        missing = required_targets - mapped_targets
        if missing:
            missing_names = [f.value for f in missing]
            raise ValueError(
                f"Missing required target fields: {missing_names}"
            )
        return v

    @field_validator("mappings")
    @classmethod
    def validate_no_duplicate_targets(cls, v: list[ColumnMapping]) -> list[ColumnMapping]:
        """Ensure no duplicate target field mappings."""
        targets = [m.target_field for m in v]
        if len(targets) != len(set(targets)):
            raise ValueError("Duplicate target field mappings")
        return v


# ---------------------------------------------------------------------------
# Inspection response
# ---------------------------------------------------------------------------


class FileInspectionResponse(BaseModel):
    """
    Response from POST /api/v1/imports/files/inspect.

    The inspection_token is used in a future mapping endpoint.
    For canonical StatFlow CSV files, direct_schema_match is true
    and suggested_mappings may be auto-generated.
    """

    inspection_token: Annotated[str, Field(
        min_length=1,
        description=(
            "Server-side token for this inspection session. "
            "Expires in 15 minutes."
        ),
    )]
    filename: Annotated[str, Field(
        description="Sanitized filename of the uploaded file.",
    )]
    source_format: Annotated[str, Field(
        description="File format detected: 'csv' for now.",
    )]
    headers: Annotated[list[str], Field(
        description="Column names extracted from the first row.",
    )]
    columns: Annotated[list[SourceColumn], Field(
        description="Inferred metadata for each column.",
    )]
    direct_schema_match: Annotated[bool, Field(
        description=(
            "True if the file uses the canonical StatFlow schema "
            "(province_code, indicator_code, value, reference_year, dataset_name). "
            "False if arbitrary columns require mapping."
        ),
    )]
    suggested_mappings: Annotated[list[ColumnMapping], Field(
        default_factory=list,
        description=(
            "Auto-suggested mappings (if implemented). "
            "Empty for Task 8A."
        ),
    )]
    warnings: Annotated[list[str], Field(
        default_factory=list,
        description="Non-fatal warnings (e.g., suspicious column names).",
    )]
    semantic_profile: Annotated[dict, Field(
        default_factory=dict,
        description="Optional serialized semantic profile detected for this file. Empty dict when unavailable.",
    )]


class ImportTemplateCreateRequest(BaseModel):
    name: Annotated[str, Field(
        min_length=1,
        max_length=200,
        description="Human-readable name for the template.",
    )]
    description: Annotated[Optional[str], Field(
        default=None,
        max_length=1000,
        description="Optional template description.",
    )]
    source_format: Annotated[str, Field(
        default="csv",
        description="Source file format for this template.",
    )]
    original_headers: Annotated[list[str], Field(
        min_items=1,
        description="Original CSV header row that produced this mapping.",
    )]
    mapping_config: Annotated[MappingConfiguration, Field(
        description="Validated mapping configuration to apply during import.",
    )]


class ImportTemplateUpdateRequest(BaseModel):
    name: Annotated[Optional[str], Field(
        default=None,
        min_length=1,
        max_length=200,
        description="Updated human-readable name for the template.",
    )]
    description: Annotated[Optional[str], Field(
        default=None,
        max_length=1000,
        description="Updated optional template description.",
    )]
    source_format: Annotated[Optional[str], Field(
        default=None,
        description="Updated source file format for this template.",
    )]
    original_headers: Annotated[Optional[list[str]], Field(
        default=None,
        min_items=1,
        description="Updated original CSV header row that produced this mapping.",
    )]
    mapping_config: Annotated[Optional[MappingConfiguration], Field(
        default=None,
        description="Updated validated mapping configuration to apply during import.",
    )]


class ImportTemplateResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    owner_id: uuid.UUID
    name: str
    description: Optional[str]
    source_format: str
    mapping_config: MappingConfiguration
    original_headers: list[str]
    is_active: bool
    created_at: datetime
    updated_at: datetime


class ImportTemplateListResponse(BaseModel):
    templates: list[ImportTemplateResponse]


# ---------------------------------------------------------------------------
# Error responses
# ---------------------------------------------------------------------------


class ImportErrorDetail(BaseModel):
    """Machine-readable error details for import validation failures."""

    code: Annotated[str, Field(
        description=(
            "Stable machine-readable error code (e.g., 'IMPORT_FILE_TOO_LARGE'). "
            "Can be used by frontend for i18n or specialized handling."
        ),
    )]
    message: Annotated[str, Field(
        description="User-facing error message.",
    )]
    details: Annotated[dict, Field(
        default_factory=dict,
        description=(
            "Additional context (e.g., missing fields, actual file size). "
            "Structure varies by error code."
        ),
    )]


# ---------------------------------------------------------------------------
# Map-preview request / response
# ---------------------------------------------------------------------------


class MapPreviewRequest(BaseModel):
    """Request body for POST /api/v1/imports/files/map-preview."""

    inspection_token: Annotated[str, Field(
        min_length=1,
        description=(
            "The inspection_token returned by POST /imports/files/inspect. "
            "Expires 15 minutes after inspection."
        ),
    )]
    mapping_config: Annotated[MappingConfiguration, Field(
        description="The mapping configuration to preview against the inspected file.",
    )]


class MapPreviewResponse(BaseModel):
    """Response body for POST /api/v1/imports/files/map-preview."""

    transformed_rows: Annotated[list[dict], Field(
        description=(
            "Each dict maps canonical target field names to their transformed values. "
            "One entry per sample row from the inspection session."
        ),
    )]
    total_preview_rows: Annotated[int, Field(
        ge=0,
        description="Number of sample rows that were processed.",
    )]
    mapped_column_count: Annotated[int, Field(
        ge=0,
        description="Number of ColumnMappings applied.",
    )]
    original_headers: Annotated[list[str], Field(
        description="Source CSV header names from the inspection session.",
    )]
    target_fields: Annotated[list[str], Field(
        description="Canonical target field names produced by this mapping.",
    )]
    mapped_preview_token: Annotated[Optional[str], Field(
        default=None,
        description=(
            "Short-lived server token for the mapped preview. "
            "Used to confirm the preview when creating persistent datasets."
        ),
    )]


class ConfirmMappedImportRequest(BaseModel):
    mapped_preview_token: Annotated[str, Field(
        min_length=1,
        description="Mapped-preview token returned by map-preview.",
    )]
    name: Annotated[str, Field(
        min_length=1,
        description="Human-readable dataset name to persist.",
    )]
    description: Annotated[Optional[str], Field(
        default=None,
        description="Optional dataset description.",
    )]


class ConfirmMappedImportResponse(BaseModel):
    dataset_id: uuid.UUID
    version_id: uuid.UUID
    name: str
    version_number: int
    row_count: int
    column_count: int
    source_filename: str
    status: str
    created_at: datetime
