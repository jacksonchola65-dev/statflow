"""
tests/test_mapped_preview_token_store.py
=====================================
Focused tests for the mapped-preview token lifecycle stored in
`app.services.mapped_preview_service` and created by
`MappingExecutionService.generate_mapping_preview()`.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from app.services.mapped_preview_service import (
    _MAPPED_PREVIEW_STORE,
    _retrieve_mapped_preview_token,
    _MappedPreviewEntry,
    MappedPreviewTokenNotFoundError,
    MappedPreviewTokenExpiredError,
    MappedPreviewTokenForbiddenError,
)
from app.services.file_inspection_service import (
    CachedInspection,
    _INSPECTION_STORE,
    _InspectionTokenEntry,
    TOKEN_TTL,
)
from app.services.mapping_execution_service import (
    MappingExecutionService,
)
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


def _make_col(name: str, samples: list[str]) -> SourceColumn:
    return SourceColumn(
        name=name,
        inferred_type=SourceColumnType.STRING,
        sample_values=samples,
        nullable=False,
        position=1,
    )


def _store_inspection(owner_id: uuid.UUID, headers: list[str], columns: list[SourceColumn], age_minutes: float = 0) -> str:
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


def _col_mapping(target: TargetField, col: str, ops: list[TransformationOperation] | None = None) -> ColumnMapping:
    return ColumnMapping(
        target_field=target,
        source_type=MappingSourceType.COLUMN,
        source_column=col,
        fixed_value=None,
        transformations=[TransformationRule(operation=op) for op in (ops or [])],
    )


def _fix_mapping(target: TargetField, value: str, ops: list[TransformationOperation] | None = None) -> ColumnMapping:
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


@pytest.fixture(autouse=True)
def cleanup_stores():
    yield
    _ISS = list(_INSPECTION_STORE.keys())
    for k in _ISS:
        _INSPECTION_STORE.pop(k, None)
    _MAPPED_PREVIEW_STORE.clear()


async def test_successful_retrieval_by_owner_and_payload_preserved():
    owner_id = uuid.uuid4()
    headers = ["region", "revenue"]
    cols = [_make_col("region", ["Lusaka"]), _make_col("revenue", ["100"])]
    token = _store_inspection(owner_id, headers, cols)

    cfg = _valid_cfg(
        _col_mapping(TargetField.PROVINCE_CODE, "region"),
        _fix_mapping(TargetField.INDICATOR_CODE, "IND"),
        _col_mapping(TargetField.VALUE, "revenue"),
        _fix_mapping(TargetField.REFERENCE_YEAR, "2024"),
        _fix_mapping(TargetField.DATASET_NAME, "DS"),
    )

    svc = _svc_mock()
    result = await svc.generate_mapping_preview(token, owner_id, cfg)
    mp_token = result.mapped_preview_token
    assert mp_token and isinstance(mp_token, str)

    payload = _retrieve_mapped_preview_token(mp_token, owner_id)
    assert payload.transformed_rows == result.transformed_rows
    assert payload.mapping_configuration == cfg
    assert payload.source_filename == "orders.csv"
    assert payload.original_headers == headers

    # created_at available via internal store; expires_at computed from TOKEN_TTL
    entry = _MAPPED_PREVIEW_STORE.get(mp_token)
    assert isinstance(entry, _MappedPreviewEntry)
    assert entry.created_at is not None
    expires_at = entry.created_at + TOKEN_TTL
    assert expires_at > entry.created_at


async def test_missing_token_raises():
    with pytest.raises(MappedPreviewTokenNotFoundError):
        _retrieve_mapped_preview_token(str(uuid.uuid4()), uuid.uuid4())


async def test_expired_token_raises_and_removed():
    owner_id = uuid.uuid4()
    headers = ["col"]
    cols = [_make_col("col", ["a"])]
    token = _store_inspection(owner_id, headers, cols)

    cfg = _valid_cfg(
        _fix_mapping(TargetField.PROVINCE_CODE, "LK"),
        _fix_mapping(TargetField.INDICATOR_CODE, "IND"),
        _fix_mapping(TargetField.VALUE, "100"),
        _fix_mapping(TargetField.REFERENCE_YEAR, "2024"),
        _fix_mapping(TargetField.DATASET_NAME, "DS"),
    )

    svc = _svc_mock()
    result = await svc.generate_mapping_preview(token, owner_id, cfg)
    mp_token = result.mapped_preview_token

    # set created_at in the past beyond TTL to simulate expiry
    entry = _MAPPED_PREVIEW_STORE.get(mp_token)
    entry.created_at = datetime.now(timezone.utc) - (TOKEN_TTL + timedelta(minutes=1))

    with pytest.raises(MappedPreviewTokenExpiredError):
        _retrieve_mapped_preview_token(mp_token, owner_id)
    # token should be removed from store
    assert mp_token not in _MAPPED_PREVIEW_STORE


async def test_wrong_owner_raises_forbidden():
    owner_id = uuid.uuid4()
    headers = ["col"]
    cols = [_make_col("col", ["a"])]
    token = _store_inspection(owner_id, headers, cols)

    cfg = _valid_cfg(
        _fix_mapping(TargetField.PROVINCE_CODE, "LK"),
        _fix_mapping(TargetField.INDICATOR_CODE, "IND"),
        _fix_mapping(TargetField.VALUE, "100"),
        _fix_mapping(TargetField.REFERENCE_YEAR, "2024"),
        _fix_mapping(TargetField.DATASET_NAME, "DS"),
    )

    svc = _svc_mock()
    result = await svc.generate_mapping_preview(token, owner_id, cfg)
    mp_token = result.mapped_preview_token

    with pytest.raises(MappedPreviewTokenForbiddenError):
        _retrieve_mapped_preview_token(mp_token, uuid.uuid4())


async def test_tokens_are_unique_and_opaque():
    owner_id = uuid.uuid4()
    headers = ["col"]
    cols = [_make_col("col", ["a"])]
    token = _store_inspection(owner_id, headers, cols)

    cfg = _valid_cfg(
        _fix_mapping(TargetField.PROVINCE_CODE, "col"),
        _fix_mapping(TargetField.INDICATOR_CODE, "IND"),
        _fix_mapping(TargetField.VALUE, "col"),
        _fix_mapping(TargetField.REFERENCE_YEAR, "2024"),
        _fix_mapping(TargetField.DATASET_NAME, "DS"),
    )

    svc = _svc_mock()
    tokens = set()
    for _ in range(5):
        result = await svc.generate_mapping_preview(token, owner_id, cfg)
        t = result.mapped_preview_token
        assert t and isinstance(t, str)
        tokens.add(t)

    assert len(tokens) == 5
