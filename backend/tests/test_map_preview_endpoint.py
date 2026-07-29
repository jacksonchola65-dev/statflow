"""
tests/test_map_preview_endpoint.py
====================================
Focused API tests for POST /api/v1/imports/files/map-preview.

Uses the authed_client fixture (real test DB, CSRF bypassed, ADMIN user).

Provinces seeded by conftest.py:
  CP Central   CB Copperbelt   EA Eastern   LP Luapula   LK Lusaka
  MU Muchinga  NW North-Western NR Northern  SO Southern  WE Western
"""

from __future__ import annotations

import sys
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

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
    CachedInspection,
    _INSPECTION_STORE,
    _InspectionTokenEntry,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

URL = "/api/v1/imports/files/map-preview"


def _store_token(
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
    created = datetime.now(timezone.utc) - timedelta(minutes=age_minutes)
    _INSPECTION_STORE[token] = _InspectionTokenEntry(payload=payload, created_at=created)
    return token


def _col(name: str, samples: list[str]) -> SourceColumn:
    return SourceColumn(
        name=name,
        inferred_type=SourceColumnType.STRING,
        sample_values=samples,
        nullable=False,
        position=1,
    )


def _mapping_body(inspection_token: str, mappings: list[dict]) -> dict:
    return {
        "inspection_token": inspection_token,
        "mapping_config": {
            "mapping_version": 1,
            "mappings": mappings,
        },
    }


def _col_m(target: str, col: str, ops: list[str] | None = None) -> dict:
    return {
        "target_field": target,
        "source_type": "column",
        "source_column": col,
        "fixed_value": None,
        "transformations": [{"operation": op} for op in (ops or [])],
        "required": True,
    }


def _fix_m(target: str, value: str, ops: list[str] | None = None) -> dict:
    return {
        "target_field": target,
        "source_type": "fixed_value",
        "source_column": None,
        "fixed_value": value,
        "transformations": [{"operation": op} for op in (ops or [])],
        "required": True,
    }


def _five_mappings(region_col: str = "region", revenue_col: str = "revenue",
                   date_col: str = "order_date") -> list[dict]:
    return [
        _col_m("province_code",  region_col),
        _fix_m("indicator_code", "ECOM_REVENUE"),
        _col_m("value",          revenue_col),
        _col_m("reference_year", date_col),
        _fix_m("dataset_name",   "Ecommerce Sales"),
    ]


@pytest.fixture(autouse=True)
def cleanup_tokens():
    inserted: list[str] = []
    yield inserted
    for tok in inserted:
        _INSPECTION_STORE.pop(tok, None)


# ---------------------------------------------------------------------------
# Successful mapped preview
# ---------------------------------------------------------------------------


async def test_successful_map_preview(authed_client, cleanup_tokens):
    from app.core.dependencies import get_current_user as _gcu
    # Get the owner_id of the authed user by introspecting the override
    # (authed_client fixture creates a real user)
    app_overrides = authed_client._transport.app.dependency_overrides
    user = await app_overrides[_gcu]()
    owner_id = user.id

    headers = ["region", "revenue", "order_date"]
    columns = [
        _col("region",     ["Lusaka",      "Central"]),
        _col("revenue",    ["2500",        "1800"]),
        _col("order_date", ["2024-01-15",  "2023-06-30"]),
    ]
    token = _store_token(owner_id, headers, columns)
    cleanup_tokens.append(token)

    resp = await authed_client.post(URL, json=_mapping_body(token, _five_mappings()))

    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["total_preview_rows"] == 2
    assert data["mapped_column_count"] == 5
    assert data["original_headers"] == headers
    assert set(data["target_fields"]) == {
        "province_code", "indicator_code", "value", "reference_year", "dataset_name"
    }
    assert len(data["transformed_rows"]) == 2
    assert data["transformed_rows"][0]["indicator_code"] == "ECOM_REVENUE"


# ---------------------------------------------------------------------------
# Missing inspection token (pydantic validation → 422)
# ---------------------------------------------------------------------------


async def test_missing_inspection_token_returns_422(authed_client):
    body = {
        "mapping_config": {
            "mapping_version": 1,
            "mappings": [_fix_m("province_code", "LK"),
                         _fix_m("indicator_code", "IND"),
                         _fix_m("value", "100"),
                         _fix_m("reference_year", "2024"),
                         _fix_m("dataset_name", "DS")],
        }
    }
    resp = await authed_client.post(URL, json=body)
    assert resp.status_code == 422


# ---------------------------------------------------------------------------
# Invalid mapping configuration
# ---------------------------------------------------------------------------


async def test_invalid_mapping_config_missing_required_fields(authed_client, cleanup_tokens):
    from app.core.dependencies import get_current_user as _gcu
    app_overrides = authed_client._transport.app.dependency_overrides
    user = await app_overrides[_gcu]()
    owner_id = user.id

    token = _store_token(owner_id, ["x"], [_col("x", ["a"])])
    cleanup_tokens.append(token)

    body = {
        "inspection_token": token,
        "mapping_config": {
            "mapping_version": 1,
            "mappings": [_fix_m("source_name", "optional only")],
        },
    }
    resp = await authed_client.post(URL, json=body)
    assert resp.status_code in (400, 422)
    detail = resp.json().get("detail", {})
    code = detail.get("code", "") if isinstance(detail, dict) else str(detail)
    assert "MAPPING" in code or "INVALID" in code or "mapping" in str(detail).lower()


async def test_invalid_mapping_version_returns_400(authed_client, cleanup_tokens):
    from app.core.dependencies import get_current_user as _gcu
    app_overrides = authed_client._transport.app.dependency_overrides
    user = await app_overrides[_gcu]()
    owner_id = user.id

    token = _store_token(owner_id, ["x"], [_col("x", ["a"])])
    cleanup_tokens.append(token)

    body = {
        "inspection_token": token,
        "mapping_config": {
            "mapping_version": 2,
            "mappings": [_fix_m("province_code", "LK"),
                         _fix_m("indicator_code", "IND"),
                         _fix_m("value", "100"),
                         _fix_m("reference_year", "2024"),
                         _fix_m("dataset_name", "DS")],
        },
    }
    resp = await authed_client.post(URL, json=body)
    assert resp.status_code == 400
    detail = resp.json()["detail"]
    assert detail["code"] == "IMPORT_INVALID_MAPPING"


# ---------------------------------------------------------------------------
# Expired / nonexistent inspection token
# ---------------------------------------------------------------------------


async def test_nonexistent_token_returns_404(authed_client):
    resp = await authed_client.post(
        URL,
        json=_mapping_body(
            str(uuid.uuid4()),
            [_fix_m("province_code", "LK"),
             _fix_m("indicator_code", "IND"),
             _fix_m("value", "100"),
             _fix_m("reference_year", "2024"),
             _fix_m("dataset_name", "DS")],
        ),
    )
    assert resp.status_code == 404
    assert resp.json()["detail"]["code"] == "IMPORT_INSPECTION_EXPIRED"


async def test_expired_token_returns_404(authed_client, cleanup_tokens):
    from app.core.dependencies import get_current_user as _gcu
    app_overrides = authed_client._transport.app.dependency_overrides
    user = await app_overrides[_gcu]()
    owner_id = user.id

    token = _store_token(owner_id, ["x"], [_col("x", ["a"])], age_minutes=16)
    cleanup_tokens.append(token)

    resp = await authed_client.post(
        URL,
        json=_mapping_body(
            token,
            [_fix_m("province_code", "LK"),
             _fix_m("indicator_code", "IND"),
             _fix_m("value", "100"),
             _fix_m("reference_year", "2024"),
             _fix_m("dataset_name", "DS")],
        ),
    )
    assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Wrong inspection owner
# ---------------------------------------------------------------------------


async def test_wrong_owner_returns_403(authed_client, cleanup_tokens):
    other_owner = uuid.uuid4()   # different from the authed user
    token = _store_token(other_owner, ["x"], [_col("x", ["a"])])
    cleanup_tokens.append(token)

    resp = await authed_client.post(
        URL,
        json=_mapping_body(
            token,
            [_fix_m("province_code", "LK"),
             _fix_m("indicator_code", "IND"),
             _fix_m("value", "100"),
             _fix_m("reference_year", "2024"),
             _fix_m("dataset_name", "DS")],
        ),
    )
    assert resp.status_code == 403
    assert resp.json()["detail"]["code"] == "IMPORT_INSPECTION_FORBIDDEN"


# ---------------------------------------------------------------------------
# Missing source column
# ---------------------------------------------------------------------------


async def test_missing_source_column_returns_422(authed_client, cleanup_tokens):
    from app.core.dependencies import get_current_user as _gcu
    app_overrides = authed_client._transport.app.dependency_overrides
    user = await app_overrides[_gcu]()
    owner_id = user.id

    # Only "revenue" column in the inspection, but mapping references "nonexistent"
    token = _store_token(owner_id, ["revenue"], [_col("revenue", ["100"])])
    cleanup_tokens.append(token)

    resp = await authed_client.post(
        URL,
        json=_mapping_body(
            token,
            [_col_m("province_code",  "nonexistent"),
             _fix_m("indicator_code", "IND"),
             _col_m("value",          "revenue"),
             _fix_m("reference_year", "2024"),
             _fix_m("dataset_name",   "DS")],
        ),
    )
    assert resp.status_code == 422
    detail = resp.json()["detail"]
    assert detail["code"] == "IMPORT_SOURCE_COLUMN_NOT_FOUND"
    assert "nonexistent" in detail["details"]["column_name"]


# ---------------------------------------------------------------------------
# Transformation execution failure
# ---------------------------------------------------------------------------


async def test_transformation_failure_returns_422(authed_client, cleanup_tokens):
    from app.core.dependencies import get_current_user as _gcu
    app_overrides = authed_client._transport.app.dependency_overrides
    user = await app_overrides[_gcu]()
    owner_id = user.id

    # "revenue" cell contains text — parse_number will fail
    token = _store_token(owner_id, ["revenue"], [_col("revenue", ["not_a_number"])])
    cleanup_tokens.append(token)

    resp = await authed_client.post(
        URL,
        json=_mapping_body(
            token,
            [_fix_m("province_code",  "LK"),
             _fix_m("indicator_code", "IND"),
             _col_m("value", "revenue", ops=["parse_number"]),
             _fix_m("reference_year", "2024"),
             _fix_m("dataset_name",   "DS")],
        ),
    )
    assert resp.status_code == 422
    detail = resp.json()["detail"]
    assert detail["code"] == "IMPORT_MAPPING_EXECUTION_FAILED"
    assert detail["details"]["operation"] == "parse_number"


# ---------------------------------------------------------------------------
# Response contract
# ---------------------------------------------------------------------------


async def test_response_contract_shape(authed_client, cleanup_tokens):
    from app.core.dependencies import get_current_user as _gcu
    app_overrides = authed_client._transport.app.dependency_overrides
    user = await app_overrides[_gcu]()
    owner_id = user.id

    token = _store_token(owner_id, ["col"], [_col("col", ["a"])])
    cleanup_tokens.append(token)

    resp = await authed_client.post(
        URL,
        json=_mapping_body(
            token,
            [_col_m("province_code",  "col"),
             _fix_m("indicator_code", "IND"),
             _col_m("value",          "col"),
             _fix_m("reference_year", "2024"),
             _fix_m("dataset_name",   "DS")],
        ),
    )
    assert resp.status_code == 200
    data = resp.json()
    # All five required response keys must be present
    for key in ("transformed_rows", "total_preview_rows", "mapped_column_count",
                "original_headers", "target_fields", "mapped_preview_token"):
        assert key in data, f"Missing key '{key}' in response"
    assert isinstance(data["transformed_rows"], list)
    assert isinstance(data["total_preview_rows"], int)
    assert isinstance(data["mapped_column_count"], int)
    assert isinstance(data["original_headers"], list)
    assert isinstance(data["target_fields"], list)


# ---------------------------------------------------------------------------
# No database insertion
# ---------------------------------------------------------------------------


async def test_no_database_insertion(authed_client, db_session, cleanup_tokens):
    """map-preview must never insert DataPoints or Datasets."""
    from sqlalchemy import select, func
    from app.models.data_point import DataPoint
    from app.models.dataset import Dataset

    from app.core.dependencies import get_current_user as _gcu
    app_overrides = authed_client._transport.app.dependency_overrides
    user = await app_overrides[_gcu]()
    owner_id = user.id

    before_dp = (await db_session.execute(
        select(func.count()).select_from(DataPoint)
    )).scalar()
    before_ds = (await db_session.execute(
        select(func.count()).select_from(Dataset)
    )).scalar()

    token = _store_token(owner_id, ["rev"], [_col("rev", ["100", "200"])])
    cleanup_tokens.append(token)

    await authed_client.post(
        URL,
        json=_mapping_body(
            token,
            [_fix_m("province_code",  "LK"),
             _fix_m("indicator_code", "IND"),
             _col_m("value",          "rev"),
             _fix_m("reference_year", "2024"),
             _fix_m("dataset_name",   "DS")],
        ),
    )

    after_dp = (await db_session.execute(
        select(func.count()).select_from(DataPoint)
    )).scalar()
    after_ds = (await db_session.execute(
        select(func.count()).select_from(Dataset)
    )).scalar()

    assert after_dp == before_dp, "DataPoints were inserted — they should not be"
    assert after_ds == before_ds, "Datasets were inserted — they should not be"
