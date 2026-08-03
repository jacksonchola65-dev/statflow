"""
Tests for GET /api/v1/districts

Districts are not seeded globally — each test that needs district records
creates them via the db_session fixture. Codes are made unique per test
using a short uuid suffix to avoid UniqueConstraint collisions across tests
that share the same database session scope.
"""

import uuid

import pytest
from app.models.district import District
from app.models.province import Province
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _unique_code(prefix: str) -> str:
    """Generate a unique district code to avoid constraint collisions."""
    return f"{prefix}{str(uuid.uuid4())[:6].upper()}"


async def _get_province_id(db: AsyncSession, code: str) -> uuid.UUID:
    """Fetch the id of a seeded province by its code."""
    from sqlalchemy import select

    result = await db.execute(select(Province).where(Province.code == code))
    province = result.scalar_one()
    return province.id


async def _create_district(
    db: AsyncSession,
    province_id: uuid.UUID,
    code: str,
    name: str,
) -> District:
    district = District(province_id=province_id, code=code, name=name)
    db.add(district)
    await db.commit()
    await db.refresh(district)
    return district


# ---------------------------------------------------------------------------
# Tests — no districts seeded
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_districts_returns_200(authed_client: AsyncClient) -> None:
    response = await authed_client.get("/api/v1/districts")
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_list_districts_empty_by_default(authed_client: AsyncClient) -> None:
    """Districts endpoint returns a list (shared DB may contain records from other tests)."""
    response = await authed_client.get("/api/v1/districts")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


# ---------------------------------------------------------------------------
# Tests — districts created within the test
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_districts_returns_created_districts(
    authed_client: AsyncClient, db_session: AsyncSession
) -> None:
    province_id = await _get_province_id(db_session, "LK")  # Lusaka
    await _create_district(db_session, province_id, _unique_code("LK"), "Kafue")
    await _create_district(db_session, province_id, _unique_code("LK"), "Chilanga")

    response = await authed_client.get("/api/v1/districts")
    assert response.status_code == 200
    assert len(response.json()) >= 2


@pytest.mark.asyncio
async def test_list_districts_ordered_alphabetically(
    authed_client: AsyncClient, db_session: AsyncSession
) -> None:
    province_id = await _get_province_id(db_session, "LK")
    await _create_district(db_session, province_id, _unique_code("LK"), "Kafue")
    await _create_district(db_session, province_id, _unique_code("LK"), "Chilanga")
    await _create_district(db_session, province_id, _unique_code("LK"), "Lusaka")

    response = await authed_client.get("/api/v1/districts")
    names = [d["name"] for d in response.json()]
    assert names == sorted(names)


@pytest.mark.asyncio
async def test_list_districts_each_has_required_fields(
    authed_client: AsyncClient, db_session: AsyncSession
) -> None:
    province_id = await _get_province_id(db_session, "CB")  # Copperbelt
    await _create_district(db_session, province_id, _unique_code("CB"), "Kitwe")

    response = await authed_client.get("/api/v1/districts")
    districts = response.json()
    assert len(districts) >= 1
    for d in districts:
        assert "id" in d
        assert "province_id" in d
        assert "code" in d
        assert "name" in d
        assert d["id"]
        assert d["province_id"]
        assert d["code"]
        assert d["name"]


# ---------------------------------------------------------------------------
# Tests — filter by province_id
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_filter_districts_by_province_id(
    authed_client: AsyncClient, db_session: AsyncSession
) -> None:
    lusaka_id = await _get_province_id(db_session, "LK")
    copperbelt_id = await _get_province_id(db_session, "CB")

    await _create_district(db_session, lusaka_id, _unique_code("LK"), "Kafue")
    await _create_district(db_session, lusaka_id, _unique_code("LK"), "Chilanga")
    await _create_district(db_session, copperbelt_id, _unique_code("CB"), "Kitwe")

    response = await authed_client.get(f"/api/v1/districts?province_id={lusaka_id}")
    assert response.status_code == 200
    districts = response.json()
    assert len(districts) >= 2
    assert all(d["province_id"] == str(lusaka_id) for d in districts)


@pytest.mark.asyncio
async def test_filter_by_province_returns_alphabetical_order(
    authed_client: AsyncClient, db_session: AsyncSession
) -> None:
    province_id = await _get_province_id(db_session, "SO")  # Southern
    await _create_district(db_session, province_id, _unique_code("SO"), "Mazabuka")
    await _create_district(db_session, province_id, _unique_code("SO"), "Choma")
    await _create_district(db_session, province_id, _unique_code("SO"), "Livingstone")

    response = await authed_client.get(f"/api/v1/districts?province_id={province_id}")
    names = [d["name"] for d in response.json()]
    assert names == sorted(names)


@pytest.mark.asyncio
async def test_filter_by_province_with_no_districts_returns_empty(
    authed_client: AsyncClient, db_session: AsyncSession
) -> None:
    """A valid province with no districts should return an empty list."""
    province_id = await _get_province_id(db_session, "WE")  # Western — no districts created

    response = await authed_client.get(f"/api/v1/districts?province_id={province_id}")
    assert response.status_code == 200
    assert response.json() == []


# ---------------------------------------------------------------------------
# Tests — invalid input
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_invalid_province_id_returns_422(authed_client: AsyncClient) -> None:
    """A non-UUID string for province_id should return HTTP 422."""
    response = await authed_client.get("/api/v1/districts?province_id=not-a-uuid")
    assert response.status_code == 422
