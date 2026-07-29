"""
tests/test_map_confirm_endpoint.py
=================================
Focused tests for POST /api/v1/imports/files/map-confirm which consumes
a mapped-preview token and persists a UniversalDataset via
UniversalDatasetPersistenceService.create_dataset_from_rows().
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest

from app.services.file_inspection_service import (
    CachedInspection,
    _INSPECTION_STORE,
    _InspectionTokenEntry,
)
from app.services.mapped_preview_service import _MAPPED_PREVIEW_STORE

URL_PREVIEW = "/api/v1/imports/files/map-preview"
URL_CONFIRM = "/api/v1/imports/files/map-confirm"


def _col(name: str, samples: list[str]):
    from app.schemas.ingestion_mapping import SourceColumn, SourceColumnType
    return SourceColumn(name=name, inferred_type=SourceColumnType.STRING, sample_values=samples, nullable=False, position=1)


def _store_inspection(owner_id: uuid.UUID, headers: list[str], columns: list):
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
    _INSPECTION_STORE[token] = _InspectionTokenEntry(payload=payload, created_at=datetime.now(timezone.utc))
    return token


async def test_successful_confirmation_persists_dataset(authed_client, db_session):
    from app.core.dependencies import get_current_user as _gcu
    app_overrides = authed_client._transport.app.dependency_overrides
    user = await app_overrides[_gcu]()
    owner_id = user.id

    headers = ["region", "revenue"]
    columns = [_col("region", ["Lusaka"]), _col("revenue", ["100"]) ]
    token = _store_inspection(owner_id, headers, columns)

    body = {
        "inspection_token": token,
        "mapping_config": {
            "mapping_version": 1,
            "mappings": [
                {"target_field": "province_code", "source_type": "column", "source_column": "region", "fixed_value": None, "transformations": [], "required": True},
                {"target_field": "indicator_code", "source_type": "fixed_value", "source_column": None, "fixed_value": "IND", "transformations": [], "required": True},
                {"target_field": "value", "source_type": "column", "source_column": "revenue", "fixed_value": None, "transformations": [], "required": True},
                {"target_field": "reference_year", "source_type": "fixed_value", "source_column": None, "fixed_value": "2024", "transformations": [], "required": True},
                {"target_field": "dataset_name", "source_type": "fixed_value", "source_column": None, "fixed_value": "DS", "transformations": [], "required": True},
            ]
        }
    }

    resp = await authed_client.post(URL_PREVIEW, json=body)
    assert resp.status_code == 200
    data = resp.json()
    mp_token = data.get("mapped_preview_token")
    assert mp_token

    confirm_body = {"mapped_preview_token": mp_token, "name": "My Dataset", "description": "desc"}
    resp2 = await authed_client.post(URL_CONFIRM, json=confirm_body)
    assert resp2.status_code == 201, resp2.text
    data2 = resp2.json()
    assert data2["name"] == "My Dataset"
    assert data2["row_count"] >= 0

    # token consumed
    assert mp_token not in _MAPPED_PREVIEW_STORE

    # persisted dataset exists
    from sqlalchemy import select
    from app.models.universal_dataset import UniversalDataset, UniversalDatasetVersion, UniversalDatasetRow, UniversalDatasetColumn

    ds = (await db_session.execute(select(UniversalDataset).where(UniversalDataset.id == uuid.UUID(data2["dataset_id"])))).scalars().first()
    assert ds is not None
    ver = (await db_session.execute(select(UniversalDatasetVersion).where(UniversalDatasetVersion.id == uuid.UUID(data2["version_id"])))).scalars().first()
    assert ver is not None
    rows = (await db_session.execute(select(UniversalDatasetRow).where(UniversalDatasetRow.dataset_version_id == ver.id))).scalars().all()
    assert len(rows) == ver.row_count


async def test_consumed_token_cannot_be_reused(authed_client):
    # Reuse same flow: generate preview, confirm, then attempt confirm again
    from app.core.dependencies import get_current_user as _gcu
    app_overrides = authed_client._transport.app.dependency_overrides
    user = await app_overrides[_gcu]()
    owner_id = user.id

    token = _store_inspection(owner_id, ["c"], [_col("c", ["a"])])
    body = {"inspection_token": token, "mapping_config": {"mapping_version":1, "mappings":[
        {"target_field":"province_code","source_type":"column","source_column":"c","fixed_value":None,"transformations":[],"required":True},
        {"target_field":"indicator_code","source_type":"fixed_value","source_column":None,"fixed_value":"IND","transformations":[],"required":True},
        {"target_field":"value","source_type":"column","source_column":"c","fixed_value":None,"transformations":[],"required":True},
        {"target_field":"reference_year","source_type":"fixed_value","source_column":None,"fixed_value":"2024","transformations":[],"required":True},
        {"target_field":"dataset_name","source_type":"fixed_value","source_column":None,"fixed_value":"DS","transformations":[],"required":True},
    ]}}
    resp = await authed_client.post(URL_PREVIEW, json=body)
    assert resp.status_code == 200
    mp = resp.json()["mapped_preview_token"]

    resp2 = await authed_client.post(URL_CONFIRM, json={"mapped_preview_token": mp, "name": "X", "description": None})
    assert resp2.status_code == 201

    # second attempt should return 404 (token not found)
    resp3 = await authed_client.post(URL_CONFIRM, json={"mapped_preview_token": mp, "name": "X2", "description": None})
    assert resp3.status_code == 404


async def test_missing_token_returns_404(authed_client):
    resp = await authed_client.post(URL_CONFIRM, json={"mapped_preview_token": str(uuid.uuid4()), "name": "A", "description": None})
    assert resp.status_code == 404


async def test_expired_token_returns_410(authed_client):
    from app.core.dependencies import get_current_user as _gcu
    app_overrides = authed_client._transport.app.dependency_overrides
    user = await app_overrides[_gcu]()
    owner_id = user.id

    token = _store_inspection(owner_id, ["c"], [_col("c", ["a"])])
    body = {"inspection_token": token, "mapping_config": {"mapping_version":1, "mappings":[
        {"target_field":"province_code","source_type":"column","source_column":"c","fixed_value":None,"transformations":[],"required":True},
        {"target_field":"indicator_code","source_type":"fixed_value","source_column":None,"fixed_value":"IND","transformations":[],"required":True},
        {"target_field":"value","source_type":"column","source_column":"c","fixed_value":None,"transformations":[],"required":True},
        {"target_field":"reference_year","source_type":"fixed_value","source_column":None,"fixed_value":"2024","transformations":[],"required":True},
        {"target_field":"dataset_name","source_type":"fixed_value","source_column":None,"fixed_value":"DS","transformations":[],"required":True},
    ]}}
    resp = await authed_client.post(URL_PREVIEW, json=body)
    mp = resp.json()["mapped_preview_token"]

    # expire it
    entry = _MAPPED_PREVIEW_STORE.get(mp)
    entry.created_at = datetime.now(timezone.utc) - timedelta(minutes=20)

    resp2 = await authed_client.post(URL_CONFIRM, json={"mapped_preview_token": mp, "name": "A", "description": None})
    assert resp2.status_code == 410


async def test_wrong_owner_returns_403(authed_client):
    # create a token for another owner directly in the _MAPPED_PREVIEW_STORE
    from app.services.mapped_preview_service import CachedMappedPreview, _store_mapped_preview_token
    other_owner = uuid.uuid4()
    payload = CachedMappedPreview(mapped_preview_token="", transformed_rows=[{"a":1}], mapping_configuration=None, source_filename="f.csv", original_headers=["a"], owner_id=other_owner)
    tok = _store_mapped_preview_token(payload)

    resp = await authed_client.post(URL_CONFIRM, json={"mapped_preview_token": tok, "name": "A", "description": None})
    assert resp.status_code == 403


async def test_blank_name_rejected(authed_client):
    # call endpoint with blank name
    resp = await authed_client.post(URL_CONFIRM, json={"mapped_preview_token": str(uuid.uuid4()), "name": "", "description": None})
    assert resp.status_code in (400, 422)


async def test_empty_cached_rows_rejected(authed_client):
    from app.services.mapped_preview_service import CachedMappedPreview, _store_mapped_preview_token
    from app.core.dependencies import get_current_user as _gcu
    app_overrides = authed_client._transport.app.dependency_overrides
    user = await app_overrides[_gcu]()
    owner_id = user.id

    payload = CachedMappedPreview(mapped_preview_token="", transformed_rows=[], mapping_configuration=None, source_filename="f.csv", original_headers=["a"], owner_id=owner_id)
    tok = _store_mapped_preview_token(payload)

    resp = await authed_client.post(URL_CONFIRM, json={"mapped_preview_token": tok, "name": "A", "description": None})
    assert resp.status_code == 422


async def test_persistence_failure_rolls_back_and_token_remains(authed_client, monkeypatch):
    # generate preview normally
    from app.core.dependencies import get_current_user as _gcu
    app_overrides = authed_client._transport.app.dependency_overrides
    user = await app_overrides[_gcu]()
    owner_id = user.id

    token = _store_inspection(owner_id, ["c"], [_col("c", ["a"])])
    body = {"inspection_token": token, "mapping_config": {"mapping_version":1, "mappings":[
        {"target_field":"province_code","source_type":"column","source_column":"c","fixed_value":None,"transformations":[],"required":True},
        {"target_field":"indicator_code","source_type":"fixed_value","source_column":None,"fixed_value":"IND","transformations":[],"required":True},
        {"target_field":"value","source_type":"column","source_column":"c","fixed_value":None,"transformations":[],"required":True},
        {"target_field":"reference_year","source_type":"fixed_value","source_column":None,"fixed_value":"2024","transformations":[],"required":True},
        {"target_field":"dataset_name","source_type":"fixed_value","source_column":None,"fixed_value":"DS","transformations":[],"required":True},
    ]}}
    resp = await authed_client.post(URL_PREVIEW, json=body)
    mp = resp.json()["mapped_preview_token"]

    # monkeypatch persistence service to raise
    import app.api.v1.endpoints.imports as imports_mod

    async def _fail_create(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(imports_mod.UniversalDatasetPersistenceService, "create_dataset_from_rows", _fail_create)

    resp2 = await authed_client.post(URL_CONFIRM, json={"mapped_preview_token": mp, "name": "FailTest", "description": None})
    assert resp2.status_code == 500

    # token should still exist
    assert mp in _MAPPED_PREVIEW_STORE
