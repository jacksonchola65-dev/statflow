"""
tests/test_generate_mapping_preview.py
=======================================
Focused tests for MappingExecutionService.generate_mapping_preview().

Covers:
- successful preview generation
- empty preview rows (no sample_values)
- fixed-value mappings
- transformation chains (trim + parse_number, trim + extract_year)
- province lookup transformation (real DB)
- invalid mapping configuration → InvalidMappingError
- invalid inspection token → InspectionNotFoundError
- ownership failure → InspectionOwnershipError
- transformation failure propagates without wrapping
- preview row order preserved
"""

from __future__ import annotations

import sys
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import MagicMock

import pytest

if sys.platform == "win32":
    import asyncio as _asyncio

    _asyncio.set_event_loop_policy(_asyncio.WindowsSelectorEventLoopPolicy())

from app.schemas.ingestion_mapping import (
    ColumnMapping,
    MappingConfiguration,
    MappingSourceType,
    SourceColumn,
    SourceColumnType,
    TargetField,
    TransformationOperation,
    TransformationRule,
)
from app.services.file_inspection_service import (
    _INSPECTION_STORE,
    CachedInspection,
    _InspectionTokenEntry,
)
from app.services.mapped_preview_service import _MAPPED_PREVIEW_STORE
from app.services.mapping_execution_service import (
    InspectionNotFoundError,
    InspectionOwnershipError,
    InvalidMappingError,
    MappingExecutionService,
    MappingPreviewResult,
    TransformationExecutionError,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_col(name: str, samples: list[str]) -> SourceColumn:
    return SourceColumn(
        name=name,
        inferred_type=SourceColumnType.STRING,
        sample_values=samples,
        nullable=False,
        position=1,
    )


def _store_inspection(
    owner_id: uuid.UUID,
    headers: list[str],
    columns: list[SourceColumn],
    age_minutes: float = 0,
) -> str:
    token = str(uuid.uuid4())
    payload = CachedInspection(
        inspection_token=token,
        filename="orders.csv",
        source_format="csv",
        headers=headers,
        columns=columns,
        direct_schema_match=False,
        suggested_mappings=[],
        warnings=[],
        owner_id=owner_id,
    )
    created_at = datetime.now(timezone.utc) - timedelta(minutes=age_minutes)
    _INSPECTION_STORE[token] = _InspectionTokenEntry(payload=payload, created_at=created_at)
    return token


def _col_mapping(
    target: TargetField, col: str, ops: list[TransformationOperation] | None = None
) -> ColumnMapping:
    return ColumnMapping(
        target_field=target,
        source_type=MappingSourceType.COLUMN,
        source_column=col,
        fixed_value=None,
        transformations=[TransformationRule(operation=op) for op in (ops or [])],
    )


def _fix_mapping(
    target: TargetField, value: str, ops: list[TransformationOperation] | None = None
) -> ColumnMapping:
    return ColumnMapping(
        target_field=target,
        source_type=MappingSourceType.FIXED_VALUE,
        source_column=None,
        fixed_value=value,
        transformations=[TransformationRule(operation=op) for op in (ops or [])],
    )


def _valid_cfg(*mappings: ColumnMapping) -> MappingConfiguration:
    return MappingConfiguration(mapping_version=1, mappings=list(mappings))


def _svc_mock() -> MappingExecutionService:
    return MappingExecutionService(session=MagicMock())


# ---------------------------------------------------------------------------
# Fixtures — clean up tokens after each test
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def cleanup_tokens():
    inserted: list[str] = []
    yield inserted
    for tok in inserted:
        _INSPECTION_STORE.pop(tok, None)
    # clear any mapped-preview tokens created by generate_mapping_preview()
    _MAPPED_PREVIEW_STORE.clear()


# ---------------------------------------------------------------------------
# Successful preview generation
# ---------------------------------------------------------------------------


async def test_successful_preview_returns_result(cleanup_tokens):
    owner_id = uuid.uuid4()
    headers = ["region", "revenue", "order_date"]
    columns = [
        _make_col("region", ["Lusaka", "Central"]),
        _make_col("revenue", ["2500", "1800"]),
        _make_col("order_date", ["2024-01-15", "2023-06-30"]),
    ]
    token = _store_inspection(owner_id, headers, columns)
    cleanup_tokens.append(token)

    cfg = _valid_cfg(
        _col_mapping(TargetField.PROVINCE_CODE, "region"),
        _fix_mapping(TargetField.INDICATOR_CODE, "ECOM_REVENUE"),
        _col_mapping(TargetField.VALUE, "revenue"),
        _col_mapping(TargetField.REFERENCE_YEAR, "order_date"),
        _fix_mapping(TargetField.DATASET_NAME, "Ecommerce Sales"),
    )

    result = await _svc_mock().generate_mapping_preview(token, owner_id, cfg)

    assert isinstance(result, MappingPreviewResult)
    assert result.mapped_preview_token is not None and result.mapped_preview_token != ""
    assert result.total_preview_rows == 2
    assert result.mapped_column_count == 5
    assert result.original_headers == headers
    assert set(result.target_fields) == {
        "province_code",
        "indicator_code",
        "value",
        "reference_year",
        "dataset_name",
    }
    assert len(result.transformed_rows) == 2


async def test_result_contains_correct_values(cleanup_tokens):
    owner_id = uuid.uuid4()
    headers = ["revenue"]
    columns = [_make_col("revenue", ["100", "200"])]
    token = _store_inspection(owner_id, headers, columns)
    cleanup_tokens.append(token)

    cfg = _valid_cfg(
        _col_mapping(TargetField.PROVINCE_CODE, "revenue"),
        _fix_mapping(TargetField.INDICATOR_CODE, "IND"),
        _col_mapping(TargetField.VALUE, "revenue"),
        _col_mapping(TargetField.REFERENCE_YEAR, "revenue"),
        _fix_mapping(TargetField.DATASET_NAME, "DS"),
    )
    result = await _svc_mock().generate_mapping_preview(token, owner_id, cfg)
    assert result.mapped_preview_token is not None and result.mapped_preview_token != ""
    assert result.transformed_rows[0]["value"] == "100"
    assert result.transformed_rows[1]["value"] == "200"


# ---------------------------------------------------------------------------
# Empty preview rows
# ---------------------------------------------------------------------------


async def test_empty_columns_returns_zero_rows(cleanup_tokens):
    owner_id = uuid.uuid4()
    token = _store_inspection(owner_id, headers=[], columns=[])
    cleanup_tokens.append(token)

    cfg = _valid_cfg(
        _fix_mapping(TargetField.PROVINCE_CODE, "LK"),
        _fix_mapping(TargetField.INDICATOR_CODE, "IND"),
        _fix_mapping(TargetField.VALUE, "100"),
        _fix_mapping(TargetField.REFERENCE_YEAR, "2024"),
        _fix_mapping(TargetField.DATASET_NAME, "DS"),
    )
    result = await _svc_mock().generate_mapping_preview(token, owner_id, cfg)
    assert result.mapped_preview_token is not None and result.mapped_preview_token != ""
    assert result.total_preview_rows == 0
    assert result.transformed_rows == []


async def test_columns_with_no_sample_values_returns_zero_rows(cleanup_tokens):
    owner_id = uuid.uuid4()
    headers = ["revenue"]
    columns = [_make_col("revenue", [])]  # empty sample_values
    token = _store_inspection(owner_id, headers, columns)
    cleanup_tokens.append(token)

    cfg = _valid_cfg(
        _col_mapping(TargetField.PROVINCE_CODE, "revenue"),
        _fix_mapping(TargetField.INDICATOR_CODE, "IND"),
        _col_mapping(TargetField.VALUE, "revenue"),
        _col_mapping(TargetField.REFERENCE_YEAR, "revenue"),
        _fix_mapping(TargetField.DATASET_NAME, "DS"),
    )
    result = await _svc_mock().generate_mapping_preview(token, owner_id, cfg)
    assert result.mapped_preview_token is not None and result.mapped_preview_token != ""
    assert result.total_preview_rows == 0


# ---------------------------------------------------------------------------
# Fixed-value mappings
# ---------------------------------------------------------------------------


async def test_fixed_value_same_across_all_rows(cleanup_tokens):
    owner_id = uuid.uuid4()
    token = _store_inspection(owner_id, ["x"], [_make_col("x", ["a", "b", "c"])])
    cleanup_tokens.append(token)

    cfg = _valid_cfg(
        _col_mapping(TargetField.PROVINCE_CODE, "x"),
        _fix_mapping(TargetField.INDICATOR_CODE, "ECOM"),
        _col_mapping(TargetField.VALUE, "x"),
        _col_mapping(TargetField.REFERENCE_YEAR, "x"),
        _fix_mapping(TargetField.DATASET_NAME, "DS"),
    )
    result = await _svc_mock().generate_mapping_preview(token, owner_id, cfg)
    assert result.mapped_preview_token is not None and result.mapped_preview_token != ""
    for row in result.transformed_rows:
        assert row["indicator_code"] == "ECOM"
        assert row["dataset_name"] == "DS"


# ---------------------------------------------------------------------------
# Transformation chains
# ---------------------------------------------------------------------------


async def test_trim_and_parse_number_transformation(cleanup_tokens):
    owner_id = uuid.uuid4()
    headers = ["revenue"]
    columns = [_make_col("revenue", ["  2500  ", "  1800.5  "])]
    token = _store_inspection(owner_id, headers, columns)
    cleanup_tokens.append(token)

    cfg = _valid_cfg(
        _fix_mapping(TargetField.PROVINCE_CODE, "LK"),
        _fix_mapping(TargetField.INDICATOR_CODE, "IND"),
        _col_mapping(
            TargetField.VALUE,
            "revenue",
            ops=[TransformationOperation.TRIM, TransformationOperation.PARSE_NUMBER],
        ),
        _fix_mapping(TargetField.REFERENCE_YEAR, "2024"),
        _fix_mapping(TargetField.DATASET_NAME, "DS"),
    )
    result = await _svc_mock().generate_mapping_preview(token, owner_id, cfg)
    assert result.mapped_preview_token is not None and result.mapped_preview_token != ""
    assert result.transformed_rows[0]["value"] == Decimal("2500")
    assert result.transformed_rows[1]["value"] == Decimal("1800.5")


async def test_trim_and_extract_year_transformation(cleanup_tokens):
    owner_id = uuid.uuid4()
    headers = ["order_date"]
    columns = [_make_col("order_date", ["  2024-06-15  ", "  2023-01-01  "])]
    token = _store_inspection(owner_id, headers, columns)
    cleanup_tokens.append(token)

    cfg = _valid_cfg(
        _fix_mapping(TargetField.PROVINCE_CODE, "LK"),
        _fix_mapping(TargetField.INDICATOR_CODE, "IND"),
        _fix_mapping(TargetField.VALUE, "100"),
        _col_mapping(
            TargetField.REFERENCE_YEAR,
            "order_date",
            ops=[TransformationOperation.TRIM, TransformationOperation.EXTRACT_YEAR],
        ),
        _fix_mapping(TargetField.DATASET_NAME, "DS"),
    )
    result = await _svc_mock().generate_mapping_preview(token, owner_id, cfg)
    assert result.mapped_preview_token is not None and result.mapped_preview_token != ""
    assert result.transformed_rows[0]["reference_year"] == 2024
    assert result.transformed_rows[1]["reference_year"] == 2023


# ---------------------------------------------------------------------------
# Province lookup transformation (real DB)
# ---------------------------------------------------------------------------


async def test_province_name_to_code_in_preview(db_session, cleanup_tokens):
    owner_id = uuid.uuid4()
    headers = ["region"]
    columns = [_make_col("region", ["Lusaka", "Central"])]
    token = _store_inspection(owner_id, headers, columns)
    cleanup_tokens.append(token)

    cfg = _valid_cfg(
        _col_mapping(
            TargetField.PROVINCE_CODE,
            "region",
            ops=[TransformationOperation.TRIM, TransformationOperation.PROVINCE_NAME_TO_CODE],
        ),
        _fix_mapping(TargetField.INDICATOR_CODE, "IND"),
        _fix_mapping(TargetField.VALUE, "100"),
        _fix_mapping(TargetField.REFERENCE_YEAR, "2024"),
        _fix_mapping(TargetField.DATASET_NAME, "DS"),
    )
    svc = MappingExecutionService(session=db_session)
    result = await svc.generate_mapping_preview(token, owner_id, cfg)
    assert result.mapped_preview_token is not None and result.mapped_preview_token != ""
    assert result.transformed_rows[0]["province_code"] == "LK"
    assert result.transformed_rows[1]["province_code"] == "CP"


# ---------------------------------------------------------------------------
# Invalid mapping configuration
# ---------------------------------------------------------------------------


async def test_invalid_mapping_raises_before_inspection(cleanup_tokens):
    """validate_mapping is called first — bad config raises without touching token store."""
    owner_id = uuid.uuid4()
    # Missing required targets — bypass Pydantic with model_construct
    cfg = MappingConfiguration.model_construct(
        mapping_version=1, mappings=[_fix_mapping(TargetField.SOURCE_NAME, "optional_only")]
    )
    # No inspection token needed — error raised before retrieval
    with pytest.raises(InvalidMappingError):
        await _svc_mock().generate_mapping_preview("any-token", owner_id, cfg)


async def test_wrong_mapping_version_raises(cleanup_tokens):
    owner_id = uuid.uuid4()
    cfg = MappingConfiguration.model_construct(
        mapping_version=2,
        mappings=[
            _fix_mapping(TargetField.PROVINCE_CODE, "LK"),
            _fix_mapping(TargetField.INDICATOR_CODE, "IND"),
            _fix_mapping(TargetField.VALUE, "100"),
            _fix_mapping(TargetField.REFERENCE_YEAR, "2024"),
            _fix_mapping(TargetField.DATASET_NAME, "DS"),
        ],
    )
    with pytest.raises(InvalidMappingError) as exc_info:
        await _svc_mock().generate_mapping_preview("any-token", owner_id, cfg)
    assert any("mapping_version" in e for e in exc_info.value.errors)


# ---------------------------------------------------------------------------
# Invalid inspection token
# ---------------------------------------------------------------------------


async def test_unknown_inspection_token_raises(cleanup_tokens):
    owner_id = uuid.uuid4()
    cfg = _valid_cfg(
        _fix_mapping(TargetField.PROVINCE_CODE, "LK"),
        _fix_mapping(TargetField.INDICATOR_CODE, "IND"),
        _fix_mapping(TargetField.VALUE, "100"),
        _fix_mapping(TargetField.REFERENCE_YEAR, "2024"),
        _fix_mapping(TargetField.DATASET_NAME, "DS"),
    )
    with pytest.raises(InspectionNotFoundError):
        await _svc_mock().generate_mapping_preview("nonexistent-token", owner_id, cfg)


async def test_expired_inspection_token_raises(cleanup_tokens):
    owner_id = uuid.uuid4()
    token = _store_inspection(owner_id, ["x"], [_make_col("x", ["a"])], age_minutes=16)
    cleanup_tokens.append(token)

    cfg = _valid_cfg(
        _fix_mapping(TargetField.PROVINCE_CODE, "LK"),
        _fix_mapping(TargetField.INDICATOR_CODE, "IND"),
        _fix_mapping(TargetField.VALUE, "100"),
        _fix_mapping(TargetField.REFERENCE_YEAR, "2024"),
        _fix_mapping(TargetField.DATASET_NAME, "DS"),
    )
    with pytest.raises(InspectionNotFoundError):
        await _svc_mock().generate_mapping_preview(token, owner_id, cfg)


# ---------------------------------------------------------------------------
# Ownership failure
# ---------------------------------------------------------------------------


async def test_wrong_owner_raises(cleanup_tokens):
    real_owner = uuid.uuid4()
    attacker = uuid.uuid4()
    token = _store_inspection(real_owner, ["x"], [_make_col("x", ["a"])])
    cleanup_tokens.append(token)

    cfg = _valid_cfg(
        _fix_mapping(TargetField.PROVINCE_CODE, "LK"),
        _fix_mapping(TargetField.INDICATOR_CODE, "IND"),
        _fix_mapping(TargetField.VALUE, "100"),
        _fix_mapping(TargetField.REFERENCE_YEAR, "2024"),
        _fix_mapping(TargetField.DATASET_NAME, "DS"),
    )
    with pytest.raises(InspectionOwnershipError):
        await _svc_mock().generate_mapping_preview(token, attacker, cfg)


# ---------------------------------------------------------------------------
# Transformation failure propagates without wrapping
# ---------------------------------------------------------------------------


async def test_transformation_failure_propagates(cleanup_tokens):
    owner_id = uuid.uuid4()
    headers = ["revenue"]
    columns = [_make_col("revenue", ["not_a_number"])]
    token = _store_inspection(owner_id, headers, columns)
    cleanup_tokens.append(token)

    cfg = _valid_cfg(
        _fix_mapping(TargetField.PROVINCE_CODE, "LK"),
        _fix_mapping(TargetField.INDICATOR_CODE, "IND"),
        _col_mapping(TargetField.VALUE, "revenue", ops=[TransformationOperation.PARSE_NUMBER]),
        _fix_mapping(TargetField.REFERENCE_YEAR, "2024"),
        _fix_mapping(TargetField.DATASET_NAME, "DS"),
    )
    with pytest.raises(TransformationExecutionError) as exc_info:
        await _svc_mock().generate_mapping_preview(token, owner_id, cfg)
    # Must be the original error, not wrapped
    assert isinstance(exc_info.value, TransformationExecutionError)
    assert exc_info.value.operation == "parse_number"


# ---------------------------------------------------------------------------
# Preview row order preserved
# ---------------------------------------------------------------------------


async def test_preview_row_order_preserved(cleanup_tokens):
    owner_id = uuid.uuid4()
    headers = ["revenue"]
    columns = [_make_col("revenue", ["100", "200", "300", "400", "500"])]
    token = _store_inspection(owner_id, headers, columns)
    cleanup_tokens.append(token)

    cfg = _valid_cfg(
        _col_mapping(TargetField.PROVINCE_CODE, "revenue"),
        _fix_mapping(TargetField.INDICATOR_CODE, "IND"),
        _col_mapping(TargetField.VALUE, "revenue"),
        _col_mapping(TargetField.REFERENCE_YEAR, "revenue"),
        _fix_mapping(TargetField.DATASET_NAME, "DS"),
    )
    result = await _svc_mock().generate_mapping_preview(token, owner_id, cfg)
    assert result.mapped_preview_token is not None and result.mapped_preview_token != ""
    values = [r["value"] for r in result.transformed_rows]
    assert values == ["100", "200", "300", "400", "500"]
