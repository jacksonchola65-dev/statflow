"""
Tests for GET /api/v1/analytics/indicator-summary

Each test builds its own minimal dependency tree:
  category → indicator → dataset → province (seeded) → data_point

Province data is drawn from the seeded provinces so we don't need to create
them. The check constraint on data_points requires exactly one of
province_id / district_id to be set.
"""
import uuid
from decimal import Decimal

import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.category import Category
from app.models.data_point import DataPoint
from app.models.dataset import Dataset
from app.models.district import District
from app.models.indicator import Indicator
from app.models.province import Province


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _uid(n: int = 8) -> str:
    return str(uuid.uuid4())[:n].upper()


async def _make_category(db: AsyncSession) -> Category:
    cat = Category(code=f"C-{_uid()}", name=f"Cat-{_uid()}")
    db.add(cat)
    await db.commit()
    await db.refresh(cat)
    return cat


async def _make_indicator(
    db: AsyncSession,
    category_id: uuid.UUID,
    unit: str = "Percent",
) -> Indicator:
    ind = Indicator(
        category_id=category_id,
        code=f"IND-{_uid()}",
        name=f"Indicator-{_uid()}",
        unit=unit,
    )
    db.add(ind)
    await db.commit()
    await db.refresh(ind)
    return ind


async def _make_dataset(db: AsyncSession) -> Dataset:
    ds = Dataset(name=f"DS-{_uid()}", is_published=True)
    db.add(ds)
    await db.commit()
    await db.refresh(ds)
    return ds


async def _get_provinces(db: AsyncSession, n: int = 2) -> list[Province]:
    result = await db.execute(select(Province).order_by(Province.name).limit(n))
    return list(result.scalars().all())


async def _make_district(db: AsyncSession, province_id: uuid.UUID) -> District:
    d = District(province_id=province_id, code=f"D-{_uid()}", name=f"Dist-{_uid()}")
    db.add(d)
    await db.commit()
    await db.refresh(d)
    return d


async def _make_province_dp(
    db: AsyncSession,
    dataset_id: uuid.UUID,
    indicator_id: uuid.UUID,
    province_id: uuid.UUID,
    year: int,
    value: Decimal = Decimal("50.0000"),
) -> DataPoint:
    dp = DataPoint(
        dataset_id=dataset_id,
        indicator_id=indicator_id,
        province_id=province_id,
        district_id=None,
        reference_year=year,
        value=value,
    )
    db.add(dp)
    await db.commit()
    await db.refresh(dp)
    return dp


async def _make_district_dp(
    db: AsyncSession,
    dataset_id: uuid.UUID,
    indicator_id: uuid.UUID,
    district_id: uuid.UUID,
    year: int,
    value: Decimal = Decimal("25.0000"),
) -> DataPoint:
    dp = DataPoint(
        dataset_id=dataset_id,
        indicator_id=indicator_id,
        district_id=district_id,
        province_id=None,
        reference_year=year,
        value=value,
    )
    db.add(dp)
    await db.commit()
    await db.refresh(dp)
    return dp


# ---------------------------------------------------------------------------
# Basic tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_indicator_summary_returns_200(
    authed_client: AsyncClient, db_session: AsyncSession
) -> None:
    cat = await _make_category(db_session)
    ind = await _make_indicator(db_session, cat.id)
    ds = await _make_dataset(db_session)
    [prov] = await _get_provinces(db_session, 1)
    await _make_province_dp(db_session, ds.id, ind.id, prov.id, 2023)

    response = await authed_client.get(
        f"/api/v1/analytics/indicator-summary"
        f"?indicator_id={ind.id}&reference_year=2023&dataset_id={ds.id}"
    )
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_indicator_summary_response_fields(
    authed_client: AsyncClient, db_session: AsyncSession
) -> None:
    cat = await _make_category(db_session)
    ind = await _make_indicator(db_session, cat.id, unit="People")
    ds = await _make_dataset(db_session)
    [prov] = await _get_provinces(db_session, 1)
    await _make_province_dp(db_session, ds.id, ind.id, prov.id, 2023, Decimal("12345.6789"))

    response = await authed_client.get(
        f"/api/v1/analytics/indicator-summary"
        f"?indicator_id={ind.id}&reference_year=2023&dataset_id={ds.id}"
    )
    body = response.json()
    assert body["indicator_id"] == str(ind.id)
    assert body["dataset_id"] == str(ds.id)
    assert body["reference_year"] == 2023
    assert body["unit"] == "People"
    assert "results" in body
    assert len(body["results"]) == 1

    r = body["results"][0]
    assert r["province_id"] == str(prov.id)
    assert r["province_code"] == prov.code
    assert r["province_name"] == prov.name
    assert float(r["value"]) == pytest.approx(12345.6789, rel=1e-4)


@pytest.mark.asyncio
async def test_decimal_value_serializes_correctly(
    authed_client: AsyncClient, db_session: AsyncSession
) -> None:
    cat = await _make_category(db_session)
    ind = await _make_indicator(db_session, cat.id)
    ds = await _make_dataset(db_session)
    [prov] = await _get_provinces(db_session, 1)
    await _make_province_dp(db_session, ds.id, ind.id, prov.id, 2022, Decimal("67.5000"))

    response = await authed_client.get(
        f"/api/v1/analytics/indicator-summary"
        f"?indicator_id={ind.id}&reference_year=2022&dataset_id={ds.id}"
    )
    value = response.json()["results"][0]["value"]
    assert float(value) == pytest.approx(67.5, rel=1e-4)


# ---------------------------------------------------------------------------
# Province ordering
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_results_ordered_alphabetically_by_province(
    authed_client: AsyncClient, db_session: AsyncSession
) -> None:
    cat = await _make_category(db_session)
    ind = await _make_indicator(db_session, cat.id)
    ds = await _make_dataset(db_session)
    provinces = await _get_provinces(db_session, 5)

    for prov in provinces:
        await _make_province_dp(db_session, ds.id, ind.id, prov.id, 2023)

    response = await authed_client.get(
        f"/api/v1/analytics/indicator-summary"
        f"?indicator_id={ind.id}&reference_year=2023&dataset_id={ds.id}"
    )
    names = [r["province_name"] for r in response.json()["results"]]
    assert names == sorted(names)


# ---------------------------------------------------------------------------
# dataset_id filtering
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_dataset_id_filter_returns_only_that_dataset(
    authed_client: AsyncClient, db_session: AsyncSession
) -> None:
    cat = await _make_category(db_session)
    ind = await _make_indicator(db_session, cat.id)
    ds_a = await _make_dataset(db_session)
    ds_b = await _make_dataset(db_session)
    provs = await _get_provinces(db_session, 2)

    await _make_province_dp(db_session, ds_a.id, ind.id, provs[0].id, 2023, Decimal("10.0000"))
    await _make_province_dp(db_session, ds_b.id, ind.id, provs[0].id, 2023, Decimal("99.0000"))

    response = await authed_client.get(
        f"/api/v1/analytics/indicator-summary"
        f"?indicator_id={ind.id}&reference_year=2023&dataset_id={ds_a.id}"
    )
    body = response.json()
    assert body["dataset_id"] == str(ds_a.id)
    assert len(body["results"]) == 1
    assert float(body["results"][0]["value"]) == pytest.approx(10.0, rel=1e-4)


# ---------------------------------------------------------------------------
# 404 — indicator not found
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_unknown_indicator_returns_404(authed_client: AsyncClient) -> None:
    response = await authed_client.get(
        f"/api/v1/analytics/indicator-summary"
        f"?indicator_id={uuid.uuid4()}&reference_year=2023"
    )
    assert response.status_code == 404


# ---------------------------------------------------------------------------
# Empty results
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_no_matching_rows_returns_empty_results(
    authed_client: AsyncClient, db_session: AsyncSession
) -> None:
    cat = await _make_category(db_session)
    ind = await _make_indicator(db_session, cat.id)

    response = await authed_client.get(
        f"/api/v1/analytics/indicator-summary"
        f"?indicator_id={ind.id}&reference_year=1999"
    )
    assert response.status_code == 200
    body = response.json()
    assert body["results"] == []
    assert body["indicator_id"] == str(ind.id)


# ---------------------------------------------------------------------------
# 409 — ambiguous data
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_ambiguous_data_without_dataset_id_returns_409(
    authed_client: AsyncClient, db_session: AsyncSession
) -> None:
    cat = await _make_category(db_session)
    ind = await _make_indicator(db_session, cat.id)
    ds_a = await _make_dataset(db_session)
    ds_b = await _make_dataset(db_session)
    [prov] = await _get_provinces(db_session, 1)

    # Same province/year/indicator in two different datasets
    await _make_province_dp(db_session, ds_a.id, ind.id, prov.id, 2023)
    await _make_province_dp(db_session, ds_b.id, ind.id, prov.id, 2023)

    response = await authed_client.get(
        f"/api/v1/analytics/indicator-summary"
        f"?indicator_id={ind.id}&reference_year=2023"
    )
    assert response.status_code == 409
    assert "ambiguous" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_single_dataset_without_dataset_id_does_not_return_409(
    authed_client: AsyncClient, db_session: AsyncSession
) -> None:
    cat = await _make_category(db_session)
    ind = await _make_indicator(db_session, cat.id)
    ds = await _make_dataset(db_session)
    [prov] = await _get_provinces(db_session, 1)
    await _make_province_dp(db_session, ds.id, ind.id, prov.id, 2024)

    response = await authed_client.get(
        f"/api/v1/analytics/indicator-summary"
        f"?indicator_id={ind.id}&reference_year=2024"
    )
    assert response.status_code == 200


# ---------------------------------------------------------------------------
# District-level rows excluded
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_district_level_rows_excluded(
    authed_client: AsyncClient, db_session: AsyncSession
) -> None:
    cat = await _make_category(db_session)
    ind = await _make_indicator(db_session, cat.id)
    ds = await _make_dataset(db_session)
    [prov] = await _get_provinces(db_session, 1)
    dist = await _make_district(db_session, prov.id)

    # Only a district-level data point — no province-level
    await _make_district_dp(db_session, ds.id, ind.id, dist.id, 2023)

    response = await authed_client.get(
        f"/api/v1/analytics/indicator-summary"
        f"?indicator_id={ind.id}&reference_year=2023&dataset_id={ds.id}"
    )
    assert response.status_code == 200
    assert response.json()["results"] == []


@pytest.mark.asyncio
async def test_mixed_geo_only_province_rows_returned(
    authed_client: AsyncClient, db_session: AsyncSession
) -> None:
    cat = await _make_category(db_session)
    ind = await _make_indicator(db_session, cat.id)
    ds = await _make_dataset(db_session)
    [prov] = await _get_provinces(db_session, 1)
    dist = await _make_district(db_session, prov.id)

    await _make_province_dp(db_session, ds.id, ind.id, prov.id, 2023, Decimal("88.0000"))
    await _make_district_dp(db_session, ds.id, ind.id, dist.id, 2023, Decimal("44.0000"))

    response = await authed_client.get(
        f"/api/v1/analytics/indicator-summary"
        f"?indicator_id={ind.id}&reference_year=2023&dataset_id={ds.id}"
    )
    body = response.json()
    assert len(body["results"]) == 1
    assert float(body["results"][0]["value"]) == pytest.approx(88.0, rel=1e-4)


# ---------------------------------------------------------------------------
# Validation — 422
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_invalid_indicator_uuid_returns_422(authed_client: AsyncClient) -> None:
    response = await authed_client.get(
        "/api/v1/analytics/indicator-summary?indicator_id=bad-uuid&reference_year=2023"
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_invalid_dataset_uuid_returns_422(
    authed_client: AsyncClient, db_session: AsyncSession
) -> None:
    cat = await _make_category(db_session)
    ind = await _make_indicator(db_session, cat.id)
    response = await authed_client.get(
        f"/api/v1/analytics/indicator-summary"
        f"?indicator_id={ind.id}&reference_year=2023&dataset_id=bad-uuid"
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_year_below_1900_returns_422(
    authed_client: AsyncClient, db_session: AsyncSession
) -> None:
    cat = await _make_category(db_session)
    ind = await _make_indicator(db_session, cat.id)
    response = await authed_client.get(
        f"/api/v1/analytics/indicator-summary"
        f"?indicator_id={ind.id}&reference_year=1800"
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_year_above_2100_returns_422(
    authed_client: AsyncClient, db_session: AsyncSession
) -> None:
    cat = await _make_category(db_session)
    ind = await _make_indicator(db_session, cat.id)
    response = await authed_client.get(
        f"/api/v1/analytics/indicator-summary"
        f"?indicator_id={ind.id}&reference_year=2200"
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_missing_indicator_id_returns_422(authed_client: AsyncClient) -> None:
    response = await authed_client.get(
        "/api/v1/analytics/indicator-summary?reference_year=2023"
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_missing_reference_year_returns_422(
    authed_client: AsyncClient, db_session: AsyncSession
) -> None:
    cat = await _make_category(db_session)
    ind = await _make_indicator(db_session, cat.id)
    response = await authed_client.get(
        f"/api/v1/analytics/indicator-summary?indicator_id={ind.id}"
    )
    assert response.status_code == 422
