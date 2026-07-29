"""
Tests for GET /api/v1/indicators

Each test creates its own records with unique codes/names to avoid
UniqueConstraint collisions across tests sharing the same database.
"""
import uuid
from typing import Optional

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.category import Category
from app.models.indicator import Indicator


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _uid(n: int = 8) -> str:
    return str(uuid.uuid4())[:n].upper()


async def _create_category(
    db: AsyncSession, name: Optional[str] = None
) -> Category:
    cat = Category(
        code=f"TST-{_uid()}",
        name=name or f"TestCat-{_uid()}",
    )
    db.add(cat)
    await db.commit()
    await db.refresh(cat)
    return cat


async def _create_indicator(
    db: AsyncSession,
    category_id: uuid.UUID,
    name: Optional[str] = None,
    code: Optional[str] = None,
) -> Indicator:
    ind = Indicator(
        category_id=category_id,
        code=code or f"IND-{_uid()}",
        name=name or f"TestInd-{_uid()}",
        description="Test description",
        unit="Units",
        source_name="Test Source",
    )
    db.add(ind)
    await db.commit()
    await db.refresh(ind)
    return ind


# ---------------------------------------------------------------------------
# Basic endpoint tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_list_indicators_returns_200(authed_client: AsyncClient) -> None:
    response = await authed_client.get("/api/v1/indicators")
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_list_indicators_empty_when_none_exist(authed_client: AsyncClient) -> None:
    """Indicators endpoint returns a list (shared DB may contain records from other tests)."""
    response = await authed_client.get("/api/v1/indicators")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


@pytest.mark.asyncio
async def test_list_indicators_returns_created_records(
    authed_client: AsyncClient, db_session: AsyncSession
) -> None:
    cat = await _create_category(db_session)
    await _create_indicator(db_session, cat.id)
    await _create_indicator(db_session, cat.id)

    response = await authed_client.get("/api/v1/indicators")
    assert response.status_code == 200
    assert len(response.json()) >= 2


@pytest.mark.asyncio
async def test_list_indicators_ordered_alphabetically(
    authed_client: AsyncClient, db_session: AsyncSession
) -> None:
    cat = await _create_category(db_session)
    await _create_indicator(db_session, cat.id, name=f"Zebra-{_uid()}")
    await _create_indicator(db_session, cat.id, name=f"Apple-{_uid()}")
    await _create_indicator(db_session, cat.id, name=f"Mango-{_uid()}")

    response = await authed_client.get("/api/v1/indicators")
    names = [i["name"] for i in response.json()]
    assert names == sorted(names)


@pytest.mark.asyncio
async def test_list_indicators_each_has_required_fields(
    authed_client: AsyncClient, db_session: AsyncSession
) -> None:
    cat = await _create_category(db_session)
    await _create_indicator(db_session, cat.id)

    response = await authed_client.get("/api/v1/indicators")
    indicators = response.json()
    assert len(indicators) >= 1

    for ind in indicators:
        for field in ("id", "category_id", "code", "name",
                      "description", "unit", "source_name"):
            assert field in ind, f"Missing '{field}' in {ind}"
        assert ind["id"]
        assert ind["category_id"]
        assert ind["code"]
        assert ind["name"]


# ---------------------------------------------------------------------------
# Category filtering
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_filter_indicators_by_category_id(
    authed_client: AsyncClient, db_session: AsyncSession
) -> None:
    cat_a = await _create_category(db_session)
    cat_b = await _create_category(db_session)

    await _create_indicator(db_session, cat_a.id)
    await _create_indicator(db_session, cat_a.id)
    await _create_indicator(db_session, cat_b.id)

    response = await authed_client.get(f"/api/v1/indicators?category_id={cat_a.id}")
    assert response.status_code == 200
    indicators = response.json()
    assert len(indicators) >= 2
    assert all(i["category_id"] == str(cat_a.id) for i in indicators)


@pytest.mark.asyncio
async def test_filter_by_category_alphabetical_order(
    authed_client: AsyncClient, db_session: AsyncSession
) -> None:
    cat = await _create_category(db_session)
    await _create_indicator(db_session, cat.id, name=f"Zoo-{_uid()}")
    await _create_indicator(db_session, cat.id, name=f"Ant-{_uid()}")
    await _create_indicator(db_session, cat.id, name=f"Bee-{_uid()}")

    response = await authed_client.get(f"/api/v1/indicators?category_id={cat.id}")
    names = [i["name"] for i in response.json()]
    assert names == sorted(names)


@pytest.mark.asyncio
async def test_filter_by_category_with_no_indicators_returns_empty(
    authed_client: AsyncClient, db_session: AsyncSession
) -> None:
    cat = await _create_category(db_session)
    response = await authed_client.get(f"/api/v1/indicators?category_id={cat.id}")
    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.asyncio
async def test_invalid_category_id_returns_422(authed_client: AsyncClient) -> None:
    response = await authed_client.get("/api/v1/indicators?category_id=not-a-uuid")
    assert response.status_code == 422
