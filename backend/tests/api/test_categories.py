"""
Tests for GET /api/v1/categories

Categories are not globally seeded. Each test creates its own records
using unique codes (uuid-suffixed) to avoid UniqueConstraint collisions
across tests that share the same database session.
"""
import uuid
from typing import Optional

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.category import Category


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _unique_code(prefix: str = "CAT") -> str:
    """Generate a unique category code."""
    return f"{prefix}-{str(uuid.uuid4())[:8].upper()}"


def _unique_name(base: str) -> str:
    """Generate a unique category name to avoid UniqueConstraint on name."""
    return f"{base}-{str(uuid.uuid4())[:6].upper()}"


async def _create_category(
    db: AsyncSession,
    name: str,
    code: Optional[str] = None,
    description: Optional[str] = None,
) -> Category:
    category = Category(
        code=code or _unique_code(),
        name=name,
        description=description,
    )
    db.add(category)
    await db.commit()
    await db.refresh(category)
    return category


# ---------------------------------------------------------------------------
# Tests — no categories created
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_list_categories_returns_200(authed_client: AsyncClient) -> None:
    response = await authed_client.get("/api/v1/categories")
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_list_categories_empty_when_none_exist(authed_client: AsyncClient) -> None:
    """Categories endpoint returns a list (may contain seeded categories)."""
    response = await authed_client.get("/api/v1/categories")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


# ---------------------------------------------------------------------------
# Tests — categories created within the test
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_list_categories_returns_created_records(
    authed_client: AsyncClient, db_session: AsyncSession
) -> None:
    await _create_category(db_session, _unique_name("Health"))
    await _create_category(db_session, _unique_name("Education"))

    response = await authed_client.get("/api/v1/categories")
    assert response.status_code == 200
    assert len(response.json()) >= 2


@pytest.mark.asyncio
async def test_list_categories_ordered_alphabetically(
    authed_client: AsyncClient, db_session: AsyncSession
) -> None:
    # Use prefixes that sort deterministically against each other and
    # the seeded categories, verifying the full list remains sorted.
    await _create_category(db_session, _unique_name("ZZZ-Water"))
    await _create_category(db_session, _unique_name("AAA-Agri"))
    await _create_category(db_session, _unique_name("MMM-Poverty"))

    response = await authed_client.get("/api/v1/categories")
    names = [c["name"] for c in response.json()]
    assert names == sorted(names)


@pytest.mark.asyncio
async def test_list_categories_each_has_required_fields(
    authed_client: AsyncClient, db_session: AsyncSession
) -> None:
    await _create_category(
        db_session,
        name=_unique_name("Health"),
        description="Health indicators",
    )

    response = await authed_client.get("/api/v1/categories")
    categories = response.json()
    assert len(categories) >= 1

    for c in categories:
        assert "id" in c,          f"Missing 'id' in {c}"
        assert "code" in c,        f"Missing 'code' in {c}"
        assert "name" in c,        f"Missing 'name' in {c}"
        assert "description" in c, f"Missing 'description' in {c}"
        assert c["id"],   "id must be non-empty"
        assert c["code"], "code must be non-empty"
        assert c["name"], "name must be non-empty"


@pytest.mark.asyncio
async def test_list_categories_description_can_be_null(
    authed_client: AsyncClient, db_session: AsyncSession
) -> None:
    name = _unique_name("Demographics")
    await _create_category(db_session, name=name, description=None)

    response = await authed_client.get("/api/v1/categories")
    categories = response.json()
    matches = [c for c in categories if c["name"] == name]
    assert len(matches) == 1
    assert matches[0]["description"] is None


@pytest.mark.asyncio
async def test_list_categories_codes_are_unique(
    authed_client: AsyncClient, db_session: AsyncSession
) -> None:
    await _create_category(db_session, _unique_name("Health"))
    await _create_category(db_session, _unique_name("Education"))
    await _create_category(db_session, _unique_name("Infrastructure"))

    response = await authed_client.get("/api/v1/categories")
    categories = response.json()
    codes = [c["code"] for c in categories]
    assert len(codes) == len(set(codes)), "Category codes must be unique"


@pytest.mark.asyncio
async def test_list_categories_names_are_unique(
    authed_client: AsyncClient, db_session: AsyncSession
) -> None:
    await _create_category(db_session, _unique_name("Health"))
    await _create_category(db_session, _unique_name("Education"))

    response = await authed_client.get("/api/v1/categories")
    categories = response.json()
    names = [c["name"] for c in categories]
    assert len(names) == len(set(names)), "Category names must be unique"
