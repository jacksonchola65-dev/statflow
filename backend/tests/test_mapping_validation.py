"""
tests/test_mapping_validation.py
==================================
Focused unit tests for MappingExecutionService.validate_mapping().

Every business rule that the method enforces has at least one passing test
and at least one failing test.

Rules under test
----------------
R1  mapping_version must be exactly 1
R2  All five required targets must be present
R3  source_name is optional (absent is valid)
R4  No target field may appear more than once
R5a source_type=column  → source_column required, fixed_value absent
R5b source_type=fixed   → fixed_value required, source_column absent
R6  Transformation operations must be from the whitelisted enum
"""

from __future__ import annotations

import sys
from unittest.mock import MagicMock

import pytest

if sys.platform == "win32":
    import asyncio as _asyncio
    _asyncio.set_event_loop_policy(_asyncio.WindowsSelectorEventLoopPolicy())

from app.schemas.ingestion_mapping import (
    ColumnMapping,
    MappingConfiguration,
    MappingSourceType,
    TargetField,
    TransformationOperation,
    TransformationRule,
)
from app.services.mapping_execution_service import (
    InvalidMappingError,
    MappingExecutionService,
    SUPPORTED_MAPPING_VERSION,
)


# ---------------------------------------------------------------------------
# Helpers — build minimal valid mappings
# ---------------------------------------------------------------------------

def _col(target: TargetField, source_column: str = "col") -> ColumnMapping:
    """Convenience: column-source mapping."""
    return ColumnMapping(
        target_field=target,
        source_type=MappingSourceType.COLUMN,
        source_column=source_column,
        fixed_value=None,
        transformations=[],
    )


def _fix(target: TargetField, fixed_value: str = "FIXED") -> ColumnMapping:
    """Convenience: fixed-value mapping."""
    return ColumnMapping(
        target_field=target,
        source_type=MappingSourceType.FIXED_VALUE,
        source_column=None,
        fixed_value=fixed_value,
        transformations=[],
    )


def _valid_config(*, version: int = 1, extra: list[ColumnMapping] | None = None) -> MappingConfiguration:
    """
    Build a fully valid MappingConfiguration covering all five required targets.
    Optionally append extra mappings (e.g. source_name).
    """
    base = [
        _col(TargetField.PROVINCE_CODE,   "region"),
        _fix(TargetField.INDICATOR_CODE,  "ECOM_REVENUE"),
        _col(TargetField.VALUE,           "revenue"),
        _col(TargetField.REFERENCE_YEAR,  "order_date"),
        _fix(TargetField.DATASET_NAME,    "Ecommerce Sales"),
    ]
    if extra:
        base.extend(extra)
    return MappingConfiguration(mapping_version=version, mappings=base)


def _stub_session() -> MagicMock:
    return MagicMock()


def _svc() -> MappingExecutionService:
    return MappingExecutionService(session=_stub_session())


# ---------------------------------------------------------------------------
# R1 — mapping_version
# ---------------------------------------------------------------------------


def test_valid_mapping_version_1_passes():
    """mapping_version=1 is the only supported version — must pass."""
    cfg = _valid_config(version=1)
    result = _svc().validate_mapping(cfg)
    assert result is cfg


def test_mapping_version_2_raises():
    """mapping_version=2 is unsupported — must raise."""
    # Build the config with version=2; Pydantic allows >= 1 so this constructs fine.
    cfg = _valid_config(version=2)
    with pytest.raises(InvalidMappingError) as exc_info:
        _svc().validate_mapping(cfg)
    assert any("mapping_version" in e for e in exc_info.value.errors)


# ---------------------------------------------------------------------------
# R2 — required targets present
# ---------------------------------------------------------------------------


def test_all_five_required_targets_passes():
    """Config with all five required targets → valid."""
    cfg = _valid_config()
    result = _svc().validate_mapping(cfg)
    assert result.mappings


def test_missing_province_code_raises():
    """Omitting province_code → InvalidMappingError listing 'province_code'."""
    mappings = [
        _fix(TargetField.INDICATOR_CODE, "IND"),
        _col(TargetField.VALUE,          "revenue"),
        _col(TargetField.REFERENCE_YEAR, "year"),
        _fix(TargetField.DATASET_NAME,   "DS"),
    ]
    # Build directly — Pydantic's own validator would reject fewer than 5 items
    # via min_items, so we bypass with model_construct + manual override.
    cfg = MappingConfiguration.model_construct(mapping_version=1, mappings=mappings)
    with pytest.raises(InvalidMappingError) as exc_info:
        _svc().validate_mapping(cfg)
    joined = " ".join(exc_info.value.errors)
    assert "province_code" in joined


def test_missing_indicator_code_raises():
    mappings = [
        _col(TargetField.PROVINCE_CODE,  "region"),
        _col(TargetField.VALUE,          "revenue"),
        _col(TargetField.REFERENCE_YEAR, "year"),
        _fix(TargetField.DATASET_NAME,   "DS"),
    ]
    cfg = MappingConfiguration.model_construct(mapping_version=1, mappings=mappings)
    with pytest.raises(InvalidMappingError) as exc_info:
        _svc().validate_mapping(cfg)
    assert "indicator_code" in " ".join(exc_info.value.errors)


def test_missing_value_raises():
    mappings = [
        _col(TargetField.PROVINCE_CODE,  "region"),
        _fix(TargetField.INDICATOR_CODE, "IND"),
        _col(TargetField.REFERENCE_YEAR, "year"),
        _fix(TargetField.DATASET_NAME,   "DS"),
    ]
    cfg = MappingConfiguration.model_construct(mapping_version=1, mappings=mappings)
    with pytest.raises(InvalidMappingError) as exc_info:
        _svc().validate_mapping(cfg)
    assert "value" in " ".join(exc_info.value.errors)


def test_missing_reference_year_raises():
    mappings = [
        _col(TargetField.PROVINCE_CODE,  "region"),
        _fix(TargetField.INDICATOR_CODE, "IND"),
        _col(TargetField.VALUE,          "revenue"),
        _fix(TargetField.DATASET_NAME,   "DS"),
    ]
    cfg = MappingConfiguration.model_construct(mapping_version=1, mappings=mappings)
    with pytest.raises(InvalidMappingError) as exc_info:
        _svc().validate_mapping(cfg)
    assert "reference_year" in " ".join(exc_info.value.errors)


def test_missing_dataset_name_raises():
    mappings = [
        _col(TargetField.PROVINCE_CODE,  "region"),
        _fix(TargetField.INDICATOR_CODE, "IND"),
        _col(TargetField.VALUE,          "revenue"),
        _col(TargetField.REFERENCE_YEAR, "year"),
    ]
    cfg = MappingConfiguration.model_construct(mapping_version=1, mappings=mappings)
    with pytest.raises(InvalidMappingError) as exc_info:
        _svc().validate_mapping(cfg)
    assert "dataset_name" in " ".join(exc_info.value.errors)


# ---------------------------------------------------------------------------
# R3 — source_name is optional
# ---------------------------------------------------------------------------


def test_source_name_absent_is_valid():
    """source_name mapping is not required — omitting it must pass."""
    cfg = _valid_config()  # no source_name mapping
    result = _svc().validate_mapping(cfg)
    assert result is cfg


def test_source_name_present_is_valid():
    """Including an optional source_name mapping is also fine."""
    cfg = _valid_config(extra=[_fix(TargetField.SOURCE_NAME, "Uploaded CSV")])
    result = _svc().validate_mapping(cfg)
    assert result is cfg


# ---------------------------------------------------------------------------
# R4 — no duplicate target fields
# ---------------------------------------------------------------------------


def test_duplicate_province_code_raises():
    """Two mappings for province_code → InvalidMappingError."""
    mappings = [
        _col(TargetField.PROVINCE_CODE,  "region"),
        _col(TargetField.PROVINCE_CODE,  "region2"),   # duplicate
        _fix(TargetField.INDICATOR_CODE, "IND"),
        _col(TargetField.VALUE,          "revenue"),
        _col(TargetField.REFERENCE_YEAR, "year"),
        _fix(TargetField.DATASET_NAME,   "DS"),
    ]
    cfg = MappingConfiguration.model_construct(mapping_version=1, mappings=mappings)
    with pytest.raises(InvalidMappingError) as exc_info:
        _svc().validate_mapping(cfg)
    assert any("province_code" in e for e in exc_info.value.errors)


def test_duplicate_value_raises():
    """Two mappings for value → InvalidMappingError."""
    mappings = [
        _col(TargetField.PROVINCE_CODE,  "region"),
        _fix(TargetField.INDICATOR_CODE, "IND"),
        _col(TargetField.VALUE,          "revenue"),
        _col(TargetField.VALUE,          "amount"),    # duplicate
        _col(TargetField.REFERENCE_YEAR, "year"),
        _fix(TargetField.DATASET_NAME,   "DS"),
    ]
    cfg = MappingConfiguration.model_construct(mapping_version=1, mappings=mappings)
    with pytest.raises(InvalidMappingError) as exc_info:
        _svc().validate_mapping(cfg)
    assert any("value" in e for e in exc_info.value.errors)


# ---------------------------------------------------------------------------
# R5a — source_type=column rules
# ---------------------------------------------------------------------------


def test_column_type_with_source_column_passes():
    """source_type=column + source_column set + no fixed_value → valid."""
    cfg = _valid_config()
    result = _svc().validate_mapping(cfg)
    assert result is cfg


def test_column_type_missing_source_column_raises():
    """
    source_type=column with an empty source_column should raise.
    We model_construct to bypass Pydantic's own validator so the
    service-layer check is exercised directly.
    """
    bad_mapping = ColumnMapping.model_construct(
        target_field=TargetField.PROVINCE_CODE,
        source_type=MappingSourceType.COLUMN,
        source_column="",          # empty — invalid
        fixed_value=None,
        transformations=[],
        required=True,
    )
    mappings = [
        bad_mapping,
        _fix(TargetField.INDICATOR_CODE, "IND"),
        _col(TargetField.VALUE,          "revenue"),
        _col(TargetField.REFERENCE_YEAR, "year"),
        _fix(TargetField.DATASET_NAME,   "DS"),
    ]
    cfg = MappingConfiguration.model_construct(mapping_version=1, mappings=mappings)
    with pytest.raises(InvalidMappingError) as exc_info:
        _svc().validate_mapping(cfg)
    assert any("source_column" in e for e in exc_info.value.errors)


def test_column_type_with_fixed_value_also_set_raises():
    """
    source_type=column but fixed_value is also populated → invalid.
    model_construct bypasses Pydantic's own mutual-exclusion validator.
    """
    bad_mapping = ColumnMapping.model_construct(
        target_field=TargetField.PROVINCE_CODE,
        source_type=MappingSourceType.COLUMN,
        source_column="region",
        fixed_value="HARDCODED",   # both set — invalid
        transformations=[],
        required=True,
    )
    mappings = [
        bad_mapping,
        _fix(TargetField.INDICATOR_CODE, "IND"),
        _col(TargetField.VALUE,          "revenue"),
        _col(TargetField.REFERENCE_YEAR, "year"),
        _fix(TargetField.DATASET_NAME,   "DS"),
    ]
    cfg = MappingConfiguration.model_construct(mapping_version=1, mappings=mappings)
    with pytest.raises(InvalidMappingError) as exc_info:
        _svc().validate_mapping(cfg)
    assert any("fixed_value" in e for e in exc_info.value.errors)


# ---------------------------------------------------------------------------
# R5b — source_type=fixed_value rules
# ---------------------------------------------------------------------------


def test_fixed_type_with_fixed_value_passes():
    """source_type=fixed_value + fixed_value set + no source_column → valid."""
    cfg = _valid_config()  # indicator_code and dataset_name use fixed_value
    result = _svc().validate_mapping(cfg)
    assert result is cfg


def test_fixed_type_missing_fixed_value_raises():
    """
    source_type=fixed_value with empty fixed_value → invalid.
    """
    bad_mapping = ColumnMapping.model_construct(
        target_field=TargetField.INDICATOR_CODE,
        source_type=MappingSourceType.FIXED_VALUE,
        source_column=None,
        fixed_value="",            # empty — invalid
        transformations=[],
        required=True,
    )
    mappings = [
        _col(TargetField.PROVINCE_CODE,  "region"),
        bad_mapping,
        _col(TargetField.VALUE,          "revenue"),
        _col(TargetField.REFERENCE_YEAR, "year"),
        _fix(TargetField.DATASET_NAME,   "DS"),
    ]
    cfg = MappingConfiguration.model_construct(mapping_version=1, mappings=mappings)
    with pytest.raises(InvalidMappingError) as exc_info:
        _svc().validate_mapping(cfg)
    assert any("fixed_value" in e for e in exc_info.value.errors)


def test_fixed_type_with_source_column_also_set_raises():
    """
    source_type=fixed_value but source_column is also populated → invalid.
    """
    bad_mapping = ColumnMapping.model_construct(
        target_field=TargetField.INDICATOR_CODE,
        source_type=MappingSourceType.FIXED_VALUE,
        source_column="some_col",  # both set — invalid
        fixed_value="ECOM_REVENUE",
        transformations=[],
        required=True,
    )
    mappings = [
        _col(TargetField.PROVINCE_CODE,  "region"),
        bad_mapping,
        _col(TargetField.VALUE,          "revenue"),
        _col(TargetField.REFERENCE_YEAR, "year"),
        _fix(TargetField.DATASET_NAME,   "DS"),
    ]
    cfg = MappingConfiguration.model_construct(mapping_version=1, mappings=mappings)
    with pytest.raises(InvalidMappingError) as exc_info:
        _svc().validate_mapping(cfg)
    assert any("source_column" in e for e in exc_info.value.errors)


# ---------------------------------------------------------------------------
# R6 — transformation operations
# ---------------------------------------------------------------------------


def test_valid_transformations_pass():
    """trim + uppercase on indicator_code column → valid."""
    mapping_with_transforms = ColumnMapping(
        target_field=TargetField.INDICATOR_CODE,
        source_type=MappingSourceType.COLUMN,
        source_column="category",
        transformations=[
            TransformationRule(operation=TransformationOperation.TRIM),
            TransformationRule(operation=TransformationOperation.UPPERCASE),
        ],
    )
    mappings = [
        _col(TargetField.PROVINCE_CODE,  "region"),
        mapping_with_transforms,
        _col(TargetField.VALUE,          "revenue"),
        _col(TargetField.REFERENCE_YEAR, "order_date"),
        _fix(TargetField.DATASET_NAME,   "DS"),
    ]
    cfg = MappingConfiguration(mapping_version=1, mappings=mappings)
    result = _svc().validate_mapping(cfg)
    assert result is cfg


def test_all_whitelisted_transformations_individually_pass():
    """Every whitelisted operation individually passes service validation."""
    for op in TransformationOperation:
        mapping = ColumnMapping(
            target_field=TargetField.VALUE,
            source_type=MappingSourceType.COLUMN,
            source_column="revenue",
            transformations=[TransformationRule(operation=op)],
        )
        mappings = [
            _col(TargetField.PROVINCE_CODE,  "region"),
            _fix(TargetField.INDICATOR_CODE, "IND"),
            mapping,
            _col(TargetField.REFERENCE_YEAR, "year"),
            _fix(TargetField.DATASET_NAME,   "DS"),
        ]
        cfg = MappingConfiguration(mapping_version=1, mappings=mappings)
        result = _svc().validate_mapping(cfg)
        assert result is cfg, f"Expected {op.value} to be valid"


def test_programmatically_injected_invalid_operation_raises():
    """
    If an unknown operation is somehow injected via model_construct
    (bypassing the Pydantic enum validator), the service must still reject it.
    """
    from unittest.mock import MagicMock

    fake_op = MagicMock()
    fake_op.value = "EXECUTE_SHELL"  # definitely not in the allowlist

    fake_transform = TransformationRule.model_construct(operation=fake_op)
    bad_mapping = ColumnMapping.model_construct(
        target_field=TargetField.VALUE,
        source_type=MappingSourceType.COLUMN,
        source_column="revenue",
        fixed_value=None,
        transformations=[fake_transform],
        required=True,
    )
    mappings = [
        _col(TargetField.PROVINCE_CODE,  "region"),
        _fix(TargetField.INDICATOR_CODE, "IND"),
        bad_mapping,
        _col(TargetField.REFERENCE_YEAR, "year"),
        _fix(TargetField.DATASET_NAME,   "DS"),
    ]
    cfg = MappingConfiguration.model_construct(mapping_version=1, mappings=mappings)
    with pytest.raises(InvalidMappingError) as exc_info:
        _svc().validate_mapping(cfg)
    assert any("EXECUTE_SHELL" in e for e in exc_info.value.errors)


# ---------------------------------------------------------------------------
# Return value contract
# ---------------------------------------------------------------------------


def test_validate_mapping_returns_same_object():
    """On success, validate_mapping returns the exact same object passed in."""
    cfg = _valid_config()
    result = _svc().validate_mapping(cfg)
    assert result is cfg


def test_multiple_errors_collected():
    """
    A config with multiple violations returns ALL errors, not just the first.
    Here: version=2 + duplicate province_code + missing dataset_name.
    """
    mappings = [
        _col(TargetField.PROVINCE_CODE, "r1"),
        _col(TargetField.PROVINCE_CODE, "r2"),   # duplicate
        _fix(TargetField.INDICATOR_CODE, "IND"),
        _col(TargetField.VALUE,          "revenue"),
        _col(TargetField.REFERENCE_YEAR, "year"),
        # dataset_name intentionally omitted
    ]
    cfg = MappingConfiguration.model_construct(mapping_version=2, mappings=mappings)
    with pytest.raises(InvalidMappingError) as exc_info:
        _svc().validate_mapping(cfg)
    errors = exc_info.value.errors
    # At minimum: version error + duplicate error + missing dataset_name
    assert len(errors) >= 3
