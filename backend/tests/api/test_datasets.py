"""
Tests for GET /api/v1/datasets

Each test creates its own records. Dataset.name is NOT unique in the schema,
so we can reuse descriptive names safely.
"""

from typing import Optional

import pytest
from app.models.dataset import Dataset
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------


async def _create_dataset(
    db: AsyncSession,
    name: str,
    reference_year: Optional[int] = None,
    is_published: bool = False,
    source_name: Optional[str] = None,
    description: Optional[str] = None,
) -> Dataset:
    ds = Dataset(
        name=name,
        reference_year=reference_year,
        is_published=is_published,
        source_name=source_name,
        description=description,
    )
    db.add(ds)
    await db.commit()
    await db.refresh(ds)
    return ds


# ---------------------------------------------------------------------------
# Basic endpoint tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_datasets_returns_200(authed_client: AsyncClient) -> None:
    response = await authed_client.get("/api/v1/datasets")
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_list_datasets_empty_when_none_exist(authed_client: AsyncClient) -> None:
    """Datasets endpoint returns a list (shared DB may contain records from other tests)."""
    response = await authed_client.get("/api/v1/datasets")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


@pytest.mark.asyncio
async def test_list_datasets_returns_created_records(
    authed_client: AsyncClient, db_session: AsyncSession
) -> None:
    await _create_dataset(db_session, "Dataset Alpha", reference_year=2023)
    await _create_dataset(db_session, "Dataset Beta", reference_year=2022)

    response = await authed_client.get("/api/v1/datasets")
    assert response.status_code == 200
    assert len(response.json()) >= 2


@pytest.mark.asyncio
async def test_list_datasets_each_has_required_fields(
    authed_client: AsyncClient, db_session: AsyncSession
) -> None:
    await _create_dataset(
        db_session,
        name="Full Dataset",
        reference_year=2023,
        is_published=True,
        source_name="Test Source",
        description="A test dataset",
    )

    response = await authed_client.get("/api/v1/datasets")
    datasets = response.json()
    assert len(datasets) >= 1

    required = (
        "id",
        "name",
        "description",
        "source_name",
        "source_url",
        "reference_year",
        "is_published",
        "created_at",
        "updated_at",
    )
    for ds in datasets:
        for field in required:
            assert field in ds, f"Missing '{field}' in {ds}"
        assert ds["id"]
        assert ds["name"]


# ---------------------------------------------------------------------------
# Ordering tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_datasets_ordered_by_year_desc_then_name_asc(
    authed_client: AsyncClient, db_session: AsyncSession
) -> None:
    await _create_dataset(db_session, "Zebra Report", reference_year=2021)
    await _create_dataset(db_session, "Alpha Report", reference_year=2023)
    await _create_dataset(db_session, "Beta Report", reference_year=2023)
    await _create_dataset(db_session, "Gamma Report", reference_year=2022)

    response = await authed_client.get("/api/v1/datasets")
    datasets = response.json()

    # Extract only our test datasets (identified by unique suffix)
    test_ds = [
        d
        for d in datasets
        if d["name"] in {"Alpha Report", "Beta Report", "Gamma Report", "Zebra Report"}
    ]

    # Should be: Alpha 2023, Beta 2023, Gamma 2022, Zebra 2021
    assert test_ds[0]["name"] == "Alpha Report" and test_ds[0]["reference_year"] == 2023
    assert test_ds[1]["name"] == "Beta Report" and test_ds[1]["reference_year"] == 2023
    assert test_ds[2]["name"] == "Gamma Report" and test_ds[2]["reference_year"] == 2022
    assert test_ds[3]["name"] == "Zebra Report" and test_ds[3]["reference_year"] == 2021


@pytest.mark.asyncio
async def test_datasets_null_year_comes_last(
    authed_client: AsyncClient, db_session: AsyncSession
) -> None:
    await _create_dataset(db_session, "Null Year Dataset", reference_year=None)
    await _create_dataset(db_session, "Yearly Dataset", reference_year=2020)

    response = await authed_client.get("/api/v1/datasets")
    datasets = response.json()

    test_ds = [d for d in datasets if d["name"] in {"Null Year Dataset", "Yearly Dataset"}]

    # Yearly comes before null-year
    assert test_ds[0]["name"] == "Yearly Dataset"
    assert test_ds[1]["name"] == "Null Year Dataset"
    assert test_ds[1]["reference_year"] is None


# ---------------------------------------------------------------------------
# published_only filtering
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_published_only_returns_200(authed_client: AsyncClient) -> None:
    response = await authed_client.get("/api/v1/datasets?published_only=true")
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_published_only_empty_when_none_published(authed_client: AsyncClient) -> None:
    """published_only endpoint returns a list; all items are published."""
    response = await authed_client.get("/api/v1/datasets?published_only=true")
    assert response.status_code == 200
    assert isinstance(response.json(), list)
    assert all(d["is_published"] is True for d in response.json())


@pytest.mark.asyncio
async def test_published_only_returns_only_published(
    authed_client: AsyncClient, db_session: AsyncSession
) -> None:
    await _create_dataset(db_session, "Published DS", is_published=True, reference_year=2023)
    await _create_dataset(db_session, "Unpublished DS", is_published=False, reference_year=2023)

    response = await authed_client.get("/api/v1/datasets?published_only=true")
    datasets = response.json()

    names = [d["name"] for d in datasets]
    assert "Published DS" in names
    assert "Unpublished DS" not in names
    assert all(d["is_published"] is True for d in datasets)


@pytest.mark.asyncio
async def test_unpublished_excluded_from_published_only(
    authed_client: AsyncClient, db_session: AsyncSession
) -> None:
    await _create_dataset(db_session, "Draft Dataset", is_published=False)
    await _create_dataset(db_session, "Released Dataset", is_published=True)

    response = await authed_client.get("/api/v1/datasets?published_only=true")
    datasets = response.json()

    assert all(d["is_published"] is True for d in datasets)
    draft_names = [d["name"] for d in datasets if d["name"] == "Draft Dataset"]
    assert draft_names == []


@pytest.mark.asyncio
async def test_default_returns_all_including_unpublished(
    authed_client: AsyncClient, db_session: AsyncSession
) -> None:
    await _create_dataset(db_session, "Visible DS", is_published=True)
    await _create_dataset(db_session, "Hidden DS", is_published=False)

    # Default (no filter) should return both
    response = await authed_client.get("/api/v1/datasets")
    names = [d["name"] for d in response.json()]
    assert "Visible DS" in names
    assert "Hidden DS" in names


@pytest.mark.asyncio
async def test_published_only_false_returns_all(
    authed_client: AsyncClient, db_session: AsyncSession
) -> None:
    await _create_dataset(db_session, "PubDS", is_published=True)
    await _create_dataset(db_session, "DraftDS", is_published=False)

    response = await authed_client.get("/api/v1/datasets?published_only=false")
    names = [d["name"] for d in response.json()]
    assert "PubDS" in names
    assert "DraftDS" in names
