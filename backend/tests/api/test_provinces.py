import pytest
from httpx import AsyncClient

EXPECTED_PROVINCE_COUNT = 10

EXPECTED_PROVINCES_ALPHA = [
    "Central",
    "Copperbelt",
    "Eastern",
    "Luapula",
    "Lusaka",
    "Muchinga",
    "North-Western",
    "Northern",
    "Southern",
    "Western",
]


@pytest.mark.asyncio
async def test_list_provinces_returns_200(authed_client: AsyncClient) -> None:
    response = await authed_client.get("/api/v1/provinces")
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_list_provinces_returns_exactly_10(authed_client: AsyncClient) -> None:
    response = await authed_client.get("/api/v1/provinces")
    provinces = response.json()
    assert len(provinces) == EXPECTED_PROVINCE_COUNT


@pytest.mark.asyncio
async def test_list_provinces_ordered_alphabetically(authed_client: AsyncClient) -> None:
    response = await authed_client.get("/api/v1/provinces")
    provinces = response.json()
    names = [p["name"] for p in provinces]
    assert names == EXPECTED_PROVINCES_ALPHA


@pytest.mark.asyncio
async def test_list_provinces_each_has_required_fields(authed_client: AsyncClient) -> None:
    response = await authed_client.get("/api/v1/provinces")
    provinces = response.json()
    for province in provinces:
        assert "id" in province, f"Missing 'id' in {province}"
        assert "code" in province, f"Missing 'code' in {province}"
        assert "name" in province, f"Missing 'name' in {province}"
        assert province["id"], "id must be non-empty"
        assert province["code"], "code must be non-empty"
        assert province["name"], "name must be non-empty"


@pytest.mark.asyncio
async def test_list_provinces_codes_are_unique(authed_client: AsyncClient) -> None:
    response = await authed_client.get("/api/v1/provinces")
    provinces = response.json()
    codes = [p["code"] for p in provinces]
    assert len(codes) == len(set(codes)), "Province codes must be unique"


@pytest.mark.asyncio
async def test_list_provinces_names_are_unique(authed_client: AsyncClient) -> None:
    response = await authed_client.get("/api/v1/provinces")
    provinces = response.json()
    names = [p["name"] for p in provinces]
    assert len(names) == len(set(names)), "Province names must be unique"
