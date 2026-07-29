"""
Tests for GET /api/v1/data-points

Every test creates its own parent records (dataset, category, indicator,
province/district) so the suite never depends on seeded development data.
DataPoint has a check constraint requiring exactly one geographic level.
"""
import uuid
from decimal import Decimal
from typing import Optional

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.category import Category
from app.models.data_point import DataPoint
from app.models.dataset import Dataset
from app.models.district import District
from app.models.indicator import Indicator
from app.models.province import Province


# ---------------------------------------------------------------------------
# Fixture helpers — create the minimal dependency tree for a DataPoint
# ---------------------------------------------------------------------------

def _uid(n: int = 8) -> str:
    return str(uuid.uuid4())[:n].upper()


async def _make_dataset(db: AsyncSession) -> Dataset:
    ds = Dataset(name=f"DS-{_uid()}", is_published=True)
    db.add(ds)
    await db.commit()
    await db.refresh(ds)
    return ds


async def _make_category(db: AsyncSession) -> Category:
    cat = Category(code=f"C-{_uid()}", name=f"Cat-{_uid()}")
    db.add(cat)
    await db.commit()
    await db.refresh(cat)
    return cat


async def _make_indicator(db: AsyncSession, category_id: uuid.UUID) -> Indicator:
    ind = Indicator(
        category_id=category_id,
        code=f"IND-{_uid()}",
        name=f"Indicator-{_uid()}",
    )
    db.add(ind)
    await db.commit()
    await db.refresh(ind)
    return ind


async def _make_province(db: AsyncSession) -> Province:
    # Re-use a seeded province by fetching the first one
    from sqlalchemy import select
    result = await db.execute(select(Province).limit(1))
    return result.scalar_one()


async def _make_district(db: AsyncSession, province_id: uuid.UUID) -> District:
    d = District(
        province_id=province_id,
        code=f"D-{_uid()}",
        name=f"District-{_uid()}",
    )
    db.add(d)
    await db.commit()
    await db.refresh(d)
    return d


async def _make_data_point(
    db: AsyncSession,
    dataset_id: uuid.UUID,
    indicator_id: uuid.UUID,
    reference_year: int,
    value: Decimal = Decimal("100.0000"),
    province_id: Optional[uuid.UUID] = None,
    district_id: Optional[uuid.UUID] = None,
) -> DataPoint:
    """
    Creates a DataPoint. Exactly one of province_id / district_id must be set.
    Defaults to using a seeded province if neither is given.
    """
    if province_id is None and district_id is None:
        from sqlalchemy import select
        result = await db.execute(select(Province).limit(1))
        province_id = result.scalar_one().id

    dp = DataPoint(
        dataset_id=dataset_id,
        indicator_id=indicator_id,
        reference_year=reference_year,
        value=value,
        province_id=province_id,
        district_id=district_id,
    )
    db.add(dp)
    await db.commit()
    await db.refresh(dp)
    return dp


# ---------------------------------------------------------------------------
# Basic endpoint tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_list_data_points_returns_200(authed_client: AsyncClient) -> None:
    response = await authed_client.get("/api/v1/data-points")
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_list_data_points_empty_when_none_exist(authed_client: AsyncClient) -> None:
    """Data points endpoint returns a list (shared DB may contain records from other tests)."""
    response = await authed_client.get("/api/v1/data-points")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


@pytest.mark.asyncio
async def test_list_data_points_returns_created_records(
    authed_client: AsyncClient, db_session: AsyncSession
) -> None:
    cat = await _make_category(db_session)
    ind = await _make_indicator(db_session, cat.id)
    ds = await _make_dataset(db_session)

    await _make_data_point(db_session, ds.id, ind.id, 2022)
    await _make_data_point(db_session, ds.id, ind.id, 2023)

    response = await authed_client.get("/api/v1/data-points")
    assert response.status_code == 200
    assert len(response.json()) >= 2


@pytest.mark.asyncio
async def test_list_data_points_each_has_required_fields(
    authed_client: AsyncClient, db_session: AsyncSession
) -> None:
    cat = await _make_category(db_session)
    ind = await _make_indicator(db_session, cat.id)
    ds = await _make_dataset(db_session)
    await _make_data_point(db_session, ds.id, ind.id, 2022, value=Decimal("42.5000"))

    response = await authed_client.get("/api/v1/data-points")
    points = response.json()
    assert len(points) >= 1

    for p in points:
        for field in ("id", "dataset_id", "indicator_id", "province_id",
                      "district_id", "value", "reference_year", "created_at"):
            assert field in p, f"Missing '{field}' in {p}"
        assert p["id"]
        assert p["value"] is not None


# ---------------------------------------------------------------------------
# Decimal serialization
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_decimal_value_serializes_correctly(
    authed_client: AsyncClient, db_session: AsyncSession
) -> None:
    cat = await _make_category(db_session)
    ind = await _make_indicator(db_session, cat.id)
    ds = await _make_dataset(db_session)
    await _make_data_point(db_session, ds.id, ind.id, 2022, value=Decimal("1234.5678"))

    response = await authed_client.get(f"/api/v1/data-points?dataset_id={ds.id}")
    points = response.json()
    assert len(points) == 1
    # Value comes back as a string representation of decimal or float
    assert float(points[0]["value"]) == pytest.approx(1234.5678, rel=1e-4)


# ---------------------------------------------------------------------------
# Ordering
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_data_points_ordered_by_year_then_created_at(
    authed_client: AsyncClient, db_session: AsyncSession
) -> None:
    cat = await _make_category(db_session)
    ind = await _make_indicator(db_session, cat.id)
    ds = await _make_dataset(db_session)

    dp2023 = await _make_data_point(db_session, ds.id, ind.id, 2023)
    dp2021 = await _make_data_point(db_session, ds.id, ind.id, 2021)
    dp2022 = await _make_data_point(db_session, ds.id, ind.id, 2022)

    response = await authed_client.get(f"/api/v1/data-points?dataset_id={ds.id}")
    points = response.json()
    years = [p["reference_year"] for p in points]
    assert years == sorted(years)


# ---------------------------------------------------------------------------
# Individual filters
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_filter_by_dataset_id(
    authed_client: AsyncClient, db_session: AsyncSession
) -> None:
    cat = await _make_category(db_session)
    ind = await _make_indicator(db_session, cat.id)
    ds_a = await _make_dataset(db_session)
    ds_b = await _make_dataset(db_session)

    await _make_data_point(db_session, ds_a.id, ind.id, 2022)
    await _make_data_point(db_session, ds_b.id, ind.id, 2022)

    response = await authed_client.get(f"/api/v1/data-points?dataset_id={ds_a.id}")
    points = response.json()
    assert len(points) == 1
    assert points[0]["dataset_id"] == str(ds_a.id)


@pytest.mark.asyncio
async def test_filter_by_indicator_id(
    authed_client: AsyncClient, db_session: AsyncSession
) -> None:
    cat = await _make_category(db_session)
    ind_a = await _make_indicator(db_session, cat.id)
    ind_b = await _make_indicator(db_session, cat.id)
    ds = await _make_dataset(db_session)

    await _make_data_point(db_session, ds.id, ind_a.id, 2022)
    await _make_data_point(db_session, ds.id, ind_b.id, 2022)

    response = await authed_client.get(f"/api/v1/data-points?indicator_id={ind_a.id}")
    points = response.json()
    assert len(points) == 1
    assert points[0]["indicator_id"] == str(ind_a.id)


@pytest.mark.asyncio
async def test_filter_by_province_id(
    authed_client: AsyncClient, db_session: AsyncSession
) -> None:
    cat = await _make_category(db_session)
    ind = await _make_indicator(db_session, cat.id)
    ds = await _make_dataset(db_session)

    from sqlalchemy import select
    result = await db_session.execute(select(Province).limit(2))
    provinces = result.scalars().all()
    prov_a, prov_b = provinces[0], provinces[1]

    await _make_data_point(db_session, ds.id, ind.id, 2022, province_id=prov_a.id)
    await _make_data_point(db_session, ds.id, ind.id, 2022, province_id=prov_b.id)

    response = await authed_client.get(f"/api/v1/data-points?province_id={prov_a.id}")
    points = response.json()
    assert all(p["province_id"] == str(prov_a.id) for p in points)
    assert any(p["dataset_id"] == str(ds.id) for p in points)


@pytest.mark.asyncio
async def test_filter_by_district_id(
    authed_client: AsyncClient, db_session: AsyncSession
) -> None:
    cat = await _make_category(db_session)
    ind = await _make_indicator(db_session, cat.id)
    ds = await _make_dataset(db_session)
    province = await _make_province(db_session)
    dist = await _make_district(db_session, province.id)

    await _make_data_point(db_session, ds.id, ind.id, 2022, district_id=dist.id)

    response = await authed_client.get(f"/api/v1/data-points?district_id={dist.id}")
    points = response.json()
    assert len(points) == 1
    assert points[0]["district_id"] == str(dist.id)


@pytest.mark.asyncio
async def test_filter_by_reference_year(
    authed_client: AsyncClient, db_session: AsyncSession
) -> None:
    cat = await _make_category(db_session)
    ind = await _make_indicator(db_session, cat.id)
    ds = await _make_dataset(db_session)

    await _make_data_point(db_session, ds.id, ind.id, 2020)
    await _make_data_point(db_session, ds.id, ind.id, 2021)
    await _make_data_point(db_session, ds.id, ind.id, 2022)

    response = await authed_client.get(
        f"/api/v1/data-points?dataset_id={ds.id}&reference_year=2021"
    )
    points = response.json()
    assert len(points) == 1
    assert points[0]["reference_year"] == 2021


# ---------------------------------------------------------------------------
# Combined filters
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_combined_dataset_and_indicator_filter(
    authed_client: AsyncClient, db_session: AsyncSession
) -> None:
    cat = await _make_category(db_session)
    ind_a = await _make_indicator(db_session, cat.id)
    ind_b = await _make_indicator(db_session, cat.id)
    ds_a = await _make_dataset(db_session)
    ds_b = await _make_dataset(db_session)

    await _make_data_point(db_session, ds_a.id, ind_a.id, 2022)
    await _make_data_point(db_session, ds_a.id, ind_b.id, 2022)
    await _make_data_point(db_session, ds_b.id, ind_a.id, 2022)

    response = await authed_client.get(
        f"/api/v1/data-points?dataset_id={ds_a.id}&indicator_id={ind_a.id}"
    )
    points = response.json()
    assert len(points) == 1
    assert points[0]["dataset_id"] == str(ds_a.id)
    assert points[0]["indicator_id"] == str(ind_a.id)


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_invalid_dataset_id_returns_422(authed_client: AsyncClient) -> None:
    response = await authed_client.get("/api/v1/data-points?dataset_id=not-a-uuid")
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_invalid_indicator_id_returns_422(authed_client: AsyncClient) -> None:
    response = await authed_client.get("/api/v1/data-points?indicator_id=not-a-uuid")
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_province_and_district_together_returns_422(
    authed_client: AsyncClient
) -> None:
    prov_id = uuid.uuid4()
    dist_id = uuid.uuid4()
    response = await authed_client.get(
        f"/api/v1/data-points?province_id={prov_id}&district_id={dist_id}"
    )
    assert response.status_code == 422
    detail = response.json().get("detail", "")
    assert "province_id" in detail.lower() or "district_id" in detail.lower()


@pytest.mark.asyncio
async def test_province_alone_does_not_return_422(authed_client: AsyncClient) -> None:
    prov_id = uuid.uuid4()
    response = await authed_client.get(f"/api/v1/data-points?province_id={prov_id}")
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_district_alone_does_not_return_422(authed_client: AsyncClient) -> None:
    dist_id = uuid.uuid4()
    response = await authed_client.get(f"/api/v1/data-points?district_id={dist_id}")
    assert response.status_code == 200
