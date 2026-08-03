"""
tests/test_data_sources.py
==========================
Integration tests for the refactored two-entity Official Data Integration module.

Tests cover:
  - DataSource (publisher): service + endpoint CRUD
  - DatasetRegistry (individual dataset): service + endpoint CRUD
  - FK relationship: dataset references a data source
  - Cannot delete a data source that still owns datasets (409)
  - Auth: reads require authentication; mutations require auth + CSRF
"""

from __future__ import annotations

import uuid as _uuid

import pytest
from app.core.config import settings
from app.core.security import create_access_token
from app.models.data_source import (
    FileFormat,
    ImportMethod,
    RefreshFrequency,
    SourceType,
    VerificationStatus,
)
from app.models.user import UserRole
from app.services.auth_service import AuthService
from app.services.data_source_service import (
    DataSourceHasDatasetsError,
    DataSourceNameConflictError,
    DataSourceNotFoundError,
    DataSourceService,
)
from app.services.dataset_registry_service import (
    DatasetNameConflictError,
    DatasetNotFoundError,
    DatasetRegistryService,
    DataSourceNotFoundForDatasetError,
)
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_CSRF = "test-csrf-ds2"


def _uid() -> str:
    return _uuid.uuid4().hex[:8]


def _source_name() -> str:
    return f"Publisher {_uid()}"


def _dataset_name() -> str:
    return f"Dataset {_uid()}"


def _admin_cookie(user_id) -> dict:
    token = create_access_token(user_id=user_id, role=UserRole.ADMIN)
    return {settings.AUTH_COOKIE_NAME: token}


def _csrf_pair() -> tuple[dict, dict]:
    return (
        {settings.CSRF_COOKIE_NAME: _CSRF},
        {settings.CSRF_HEADER_NAME: _CSRF},
    )


async def _make_admin(db_session: AsyncSession):
    svc = AuthService(db_session)
    user = await svc.create_user(
        email=f"ds-{_uid()}@example.com",
        password="correct horse battery staple",
        full_name="Test Admin",
        role=UserRole.ADMIN,
        is_active=True,
    )
    await db_session.flush()
    return user


# ===========================================================================
# DataSource SERVICE tests
# ===========================================================================


@pytest.mark.asyncio
async def test_datasource_create_and_get(db_session: AsyncSession):
    svc = DataSourceService(db_session)
    name = _source_name()
    src = await svc.create_source(
        name=name,
        description="National statistics body",
        organization_type="Government",
        country="Zambia",
    )
    await db_session.flush()

    fetched = await svc.get_source(src.id)
    assert fetched.id == src.id
    assert fetched.name == name
    assert fetched.country == "Zambia"
    assert fetched.is_active is True


@pytest.mark.asyncio
async def test_datasource_duplicate_name_raises(db_session: AsyncSession):
    svc = DataSourceService(db_session)
    name = _source_name()
    await svc.create_source(name=name)
    await db_session.flush()

    with pytest.raises(DataSourceNameConflictError):
        await svc.create_source(name=name)


@pytest.mark.asyncio
async def test_datasource_duplicate_name_case_insensitive(db_session: AsyncSession):
    svc = DataSourceService(db_session)
    name = _source_name()
    await svc.create_source(name=name)
    await db_session.flush()

    with pytest.raises(DataSourceNameConflictError):
        await svc.create_source(name=name.upper())


@pytest.mark.asyncio
async def test_datasource_update(db_session: AsyncSession):
    svc = DataSourceService(db_session)
    src = await svc.create_source(name=_source_name())
    await db_session.flush()

    updated = await svc.update_source(src.id, country="Zambia", is_active=False)
    assert updated.country == "Zambia"
    assert updated.is_active is False
    assert updated.name == src.name  # unchanged


@pytest.mark.asyncio
async def test_datasource_not_found_raises(db_session: AsyncSession):
    svc = DataSourceService(db_session)
    with pytest.raises(DataSourceNotFoundError):
        await svc.get_source(_uuid.uuid4())


@pytest.mark.asyncio
async def test_datasource_delete(db_session: AsyncSession):
    svc = DataSourceService(db_session)
    src = await svc.create_source(name=_source_name())
    await db_session.flush()

    await svc.delete_source(src.id)
    await db_session.flush()

    with pytest.raises(DataSourceNotFoundError):
        await svc.get_source(src.id)


@pytest.mark.asyncio
async def test_datasource_delete_blocked_when_datasets_exist(db_session: AsyncSession):
    """Deleting a DataSource that owns datasets must raise DataSourceHasDatasetsError."""
    src_svc = DataSourceService(db_session)
    ds_svc = DatasetRegistryService(db_session)

    src = await src_svc.create_source(name=_source_name())
    await db_session.flush()

    await ds_svc.create_dataset(
        data_source_id=src.id,
        dataset_name=_dataset_name(),
        source_type=SourceType.OFFICIAL,
    )
    await db_session.flush()

    with pytest.raises(DataSourceHasDatasetsError):
        await src_svc.delete_source(src.id)


# ===========================================================================
# DatasetRegistry SERVICE tests
# ===========================================================================


@pytest.mark.asyncio
async def test_dataset_create_and_get(db_session: AsyncSession):
    src_svc = DataSourceService(db_session)
    ds_svc = DatasetRegistryService(db_session)

    src = await src_svc.create_source(name=_source_name())
    await db_session.flush()

    name = _dataset_name()
    entry = await ds_svc.create_dataset(
        data_source_id=src.id,
        dataset_name=name,
        source_type=SourceType.OFFICIAL,
        category="Demographics",
        licence="CC BY 4.0",
    )
    await db_session.flush()

    fetched = await ds_svc.get_dataset(entry.id)
    assert fetched.id == entry.id
    assert fetched.dataset_name == name
    assert fetched.data_source_id == src.id
    assert fetched.verification_status == VerificationStatus.UNVERIFIED


@pytest.mark.asyncio
async def test_dataset_invalid_source_raises(db_session: AsyncSession):
    svc = DatasetRegistryService(db_session)
    with pytest.raises(DataSourceNotFoundForDatasetError):
        await svc.create_dataset(
            data_source_id=_uuid.uuid4(),
            dataset_name=_dataset_name(),
            source_type=SourceType.OFFICIAL,
        )


@pytest.mark.asyncio
async def test_dataset_duplicate_name_raises(db_session: AsyncSession):
    src_svc = DataSourceService(db_session)
    ds_svc = DatasetRegistryService(db_session)

    src = await src_svc.create_source(name=_source_name())
    await db_session.flush()
    name = _dataset_name()
    await ds_svc.create_dataset(
        data_source_id=src.id, dataset_name=name, source_type=SourceType.OFFICIAL
    )
    await db_session.flush()

    with pytest.raises(DatasetNameConflictError):
        await ds_svc.create_dataset(
            data_source_id=src.id, dataset_name=name, source_type=SourceType.OFFICIAL
        )


@pytest.mark.asyncio
async def test_dataset_filter_by_source(db_session: AsyncSession):
    src_svc = DataSourceService(db_session)
    ds_svc = DatasetRegistryService(db_session)

    src_a = await src_svc.create_source(name=_source_name())
    src_b = await src_svc.create_source(name=_source_name())
    await db_session.flush()

    name_a = _dataset_name()
    name_b = _dataset_name()
    await ds_svc.create_dataset(
        data_source_id=src_a.id, dataset_name=name_a, source_type=SourceType.OFFICIAL
    )
    await ds_svc.create_dataset(
        data_source_id=src_b.id, dataset_name=name_b, source_type=SourceType.OFFICIAL
    )
    await db_session.flush()

    results = await ds_svc.list_datasets(data_source_id=src_a.id)
    names = [r.dataset_name for r in results]
    assert name_a in names
    assert name_b not in names


@pytest.mark.asyncio
async def test_dataset_update(db_session: AsyncSession):
    src_svc = DataSourceService(db_session)
    ds_svc = DatasetRegistryService(db_session)

    src = await src_svc.create_source(name=_source_name())
    await db_session.flush()
    entry = await ds_svc.create_dataset(
        data_source_id=src.id,
        dataset_name=_dataset_name(),
        source_type=SourceType.OFFICIAL,
    )
    await db_session.flush()

    updated = await ds_svc.update_dataset(
        entry.id,
        verification_status=VerificationStatus.VERIFIED,
        file_format=FileFormat.CSV,
    )
    assert updated.verification_status == VerificationStatus.VERIFIED
    assert updated.file_format == FileFormat.CSV
    assert updated.source_type == SourceType.OFFICIAL  # unchanged


@pytest.mark.asyncio
async def test_dataset_not_found_raises(db_session: AsyncSession):
    svc = DatasetRegistryService(db_session)
    with pytest.raises(DatasetNotFoundError):
        await svc.get_dataset(_uuid.uuid4())


@pytest.mark.asyncio
async def test_all_metadata_fields_stored(db_session: AsyncSession):
    from datetime import date, datetime, timezone

    src_svc = DataSourceService(db_session)
    ds_svc = DatasetRegistryService(db_session)

    src = await src_svc.create_source(name=_source_name())
    await db_session.flush()

    entry = await ds_svc.create_dataset(
        data_source_id=src.id,
        dataset_name=_dataset_name(),
        source_type=SourceType.OFFICIAL,
        description="Census 2022",
        category="Demographics",
        file_format=FileFormat.CSV,
        source_url="https://zamstat.gov.zm/census2022",
        publication_date=date(2023, 6, 15),
        licence="CC BY 4.0",
        version="v1",
        import_method=ImportMethod.MANUAL,
        refresh_frequency=RefreshFrequency.ANNUALLY,
        last_imported_at=datetime(2024, 1, 1, tzinfo=timezone.utc),
        verification_status=VerificationStatus.VERIFIED,
    )
    await db_session.flush()

    fetched = await ds_svc.get_dataset(entry.id)
    assert fetched.description == "Census 2022"
    assert fetched.file_format == FileFormat.CSV
    assert fetched.import_method == ImportMethod.MANUAL
    assert fetched.verification_status == VerificationStatus.VERIFIED
    assert fetched.data_source_id == src.id


# ===========================================================================
# DataSource ENDPOINT tests
# ===========================================================================


@pytest.mark.asyncio
async def test_list_sources_returns_200(authed_client: AsyncClient):
    resp = await authed_client.get("/api/v1/data-sources")
    assert resp.status_code == 200
    body = resp.json()
    assert "sources" in body
    assert "total" in body


@pytest.mark.asyncio
async def test_list_sources_requires_auth(client: AsyncClient):
    resp = await client.get("/api/v1/data-sources")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_create_source_returns_201(authed_client: AsyncClient):
    resp = await authed_client.post(
        "/api/v1/data-sources",
        json={"name": _source_name(), "country": "Zambia"},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert "id" in body
    assert body["country"] == "Zambia"


@pytest.mark.asyncio
async def test_create_source_duplicate_409(authed_client: AsyncClient):
    name = _source_name()
    r1 = await authed_client.post("/api/v1/data-sources", json={"name": name})
    assert r1.status_code == 201
    r2 = await authed_client.post("/api/v1/data-sources", json={"name": name})
    assert r2.status_code == 409


@pytest.mark.asyncio
async def test_get_source_by_id(authed_client: AsyncClient):
    cr = await authed_client.post("/api/v1/data-sources", json={"name": _source_name()})
    assert cr.status_code == 201
    src_id = cr.json()["id"]

    gr = await authed_client.get(f"/api/v1/data-sources/{src_id}")
    assert gr.status_code == 200
    assert gr.json()["id"] == src_id


@pytest.mark.asyncio
async def test_get_source_missing_404(authed_client: AsyncClient):
    resp = await authed_client.get(f"/api/v1/data-sources/{_uuid.uuid4()}")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_update_source(authed_client: AsyncClient):
    cr = await authed_client.post("/api/v1/data-sources", json={"name": _source_name()})
    src_id = cr.json()["id"]
    pr = await authed_client.patch(
        f"/api/v1/data-sources/{src_id}",
        json={"country": "Zambia", "is_active": False},
    )
    assert pr.status_code == 200
    assert pr.json()["country"] == "Zambia"
    assert pr.json()["is_active"] is False


@pytest.mark.asyncio
async def test_delete_source_returns_204(authed_client: AsyncClient):
    cr = await authed_client.post("/api/v1/data-sources", json={"name": _source_name()})
    src_id = cr.json()["id"]
    dr = await authed_client.delete(f"/api/v1/data-sources/{src_id}")
    assert dr.status_code == 204


@pytest.mark.asyncio
async def test_delete_source_with_datasets_returns_409(authed_client: AsyncClient):
    """Deleting a source that has datasets must return 409."""
    cr = await authed_client.post("/api/v1/data-sources", json={"name": _source_name()})
    src_id = cr.json()["id"]

    # Create a dataset under this source
    await authed_client.post(
        "/api/v1/dataset-registry",
        json={
            "data_source_id": src_id,
            "dataset_name": _dataset_name(),
            "source_type": "OFFICIAL",
        },
    )

    dr = await authed_client.delete(f"/api/v1/data-sources/{src_id}")
    assert dr.status_code == 409


@pytest.mark.asyncio
async def test_create_source_requires_csrf(client: AsyncClient, db_session: AsyncSession):
    admin = await _make_admin(db_session)
    resp = await client.post(
        "/api/v1/data-sources",
        json={"name": _source_name()},
        cookies=_admin_cookie(admin.id),
        # no CSRF
    )
    assert resp.status_code == 403
    assert resp.json()["detail"] == "CSRF validation failed."


@pytest.mark.asyncio
async def test_create_source_with_csrf_succeeds(client: AsyncClient, db_session: AsyncSession):
    admin = await _make_admin(db_session)
    csrf_c, csrf_h = _csrf_pair()
    resp = await client.post(
        "/api/v1/data-sources",
        json={"name": _source_name()},
        cookies={**_admin_cookie(admin.id), **csrf_c},
        headers=csrf_h,
    )
    assert resp.status_code == 201


# ===========================================================================
# DatasetRegistry ENDPOINT tests
# ===========================================================================


@pytest.mark.asyncio
async def test_list_datasets_returns_200(authed_client: AsyncClient):
    resp = await authed_client.get("/api/v1/dataset-registry")
    assert resp.status_code == 200
    assert "datasets" in resp.json()


@pytest.mark.asyncio
async def test_list_datasets_requires_auth(client: AsyncClient):
    resp = await client.get("/api/v1/dataset-registry")
    assert resp.status_code == 401


@pytest.mark.asyncio
async def test_create_dataset_returns_201(authed_client: AsyncClient):
    # Create a source first
    cr = await authed_client.post("/api/v1/data-sources", json={"name": _source_name()})
    src_id = cr.json()["id"]

    dr = await authed_client.post(
        "/api/v1/dataset-registry",
        json={
            "data_source_id": src_id,
            "dataset_name": _dataset_name(),
            "source_type": "OFFICIAL",
        },
    )
    assert dr.status_code == 201
    body = dr.json()
    assert body["data_source_id"] == src_id
    assert body["verification_status"] == "UNVERIFIED"


@pytest.mark.asyncio
async def test_create_dataset_missing_source_404(authed_client: AsyncClient):
    dr = await authed_client.post(
        "/api/v1/dataset-registry",
        json={
            "data_source_id": str(_uuid.uuid4()),
            "dataset_name": _dataset_name(),
            "source_type": "OFFICIAL",
        },
    )
    assert dr.status_code == 404


@pytest.mark.asyncio
async def test_create_dataset_duplicate_409(authed_client: AsyncClient):
    cr = await authed_client.post("/api/v1/data-sources", json={"name": _source_name()})
    src_id = cr.json()["id"]
    name = _dataset_name()
    payload = {
        "data_source_id": src_id,
        "dataset_name": name,
        "source_type": "OFFICIAL",
    }
    r1 = await authed_client.post("/api/v1/dataset-registry", json=payload)
    assert r1.status_code == 201
    r2 = await authed_client.post("/api/v1/dataset-registry", json=payload)
    assert r2.status_code == 409


@pytest.mark.asyncio
async def test_get_dataset_by_id(authed_client: AsyncClient):
    cr = await authed_client.post("/api/v1/data-sources", json={"name": _source_name()})
    src_id = cr.json()["id"]
    dr = await authed_client.post(
        "/api/v1/dataset-registry",
        json={
            "data_source_id": src_id,
            "dataset_name": _dataset_name(),
            "source_type": "OFFICIAL",
        },
    )
    entry_id = dr.json()["id"]
    gr = await authed_client.get(f"/api/v1/dataset-registry/{entry_id}")
    assert gr.status_code == 200
    assert gr.json()["id"] == entry_id


@pytest.mark.asyncio
async def test_get_dataset_missing_404(authed_client: AsyncClient):
    resp = await authed_client.get(f"/api/v1/dataset-registry/{_uuid.uuid4()}")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_update_dataset(authed_client: AsyncClient):
    cr = await authed_client.post("/api/v1/data-sources", json={"name": _source_name()})
    src_id = cr.json()["id"]
    dr = await authed_client.post(
        "/api/v1/dataset-registry",
        json={
            "data_source_id": src_id,
            "dataset_name": _dataset_name(),
            "source_type": "OFFICIAL",
        },
    )
    entry_id = dr.json()["id"]
    pr = await authed_client.patch(
        f"/api/v1/dataset-registry/{entry_id}",
        json={"verification_status": "VERIFIED", "file_format": "CSV"},
    )
    assert pr.status_code == 200
    assert pr.json()["verification_status"] == "VERIFIED"
    assert pr.json()["file_format"] == "CSV"


@pytest.mark.asyncio
async def test_delete_dataset_returns_204(authed_client: AsyncClient):
    cr = await authed_client.post("/api/v1/data-sources", json={"name": _source_name()})
    src_id = cr.json()["id"]
    dr = await authed_client.post(
        "/api/v1/dataset-registry",
        json={
            "data_source_id": src_id,
            "dataset_name": _dataset_name(),
            "source_type": "OFFICIAL",
        },
    )
    entry_id = dr.json()["id"]
    resp = await authed_client.delete(f"/api/v1/dataset-registry/{entry_id}")
    assert resp.status_code == 204


@pytest.mark.asyncio
async def test_dataset_filter_by_data_source_id(authed_client: AsyncClient):
    cr_a = await authed_client.post("/api/v1/data-sources", json={"name": _source_name()})
    cr_b = await authed_client.post("/api/v1/data-sources", json={"name": _source_name()})
    src_a_id = cr_a.json()["id"]
    src_b_id = cr_b.json()["id"]

    name_a = _dataset_name()
    name_b = _dataset_name()
    await authed_client.post(
        "/api/v1/dataset-registry",
        json={"data_source_id": src_a_id, "dataset_name": name_a, "source_type": "OFFICIAL"},
    )
    await authed_client.post(
        "/api/v1/dataset-registry",
        json={"data_source_id": src_b_id, "dataset_name": name_b, "source_type": "OFFICIAL"},
    )

    resp = await authed_client.get("/api/v1/dataset-registry", params={"data_source_id": src_a_id})
    assert resp.status_code == 200
    names = [d["dataset_name"] for d in resp.json()["datasets"]]
    assert name_a in names
    assert name_b not in names


@pytest.mark.asyncio
async def test_create_dataset_requires_csrf(client: AsyncClient, db_session: AsyncSession):
    admin = await _make_admin(db_session)
    # Need a source — create via authed service directly
    from app.services.data_source_service import DataSourceService as _SrcSvc

    src_svc = _SrcSvc(db_session)
    src = await src_svc.create_source(name=_source_name())
    await db_session.flush()

    resp = await client.post(
        "/api/v1/dataset-registry",
        json={
            "data_source_id": str(src.id),
            "dataset_name": _dataset_name(),
            "source_type": "OFFICIAL",
        },
        cookies=_admin_cookie(admin.id),
        # no CSRF
    )
    assert resp.status_code == 403
