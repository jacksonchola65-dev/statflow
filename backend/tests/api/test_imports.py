"""
Narrowly scoped endpoint tests for the CSV import workflow.

Coverage:
    - valid preview (200)
    - invalid MIME type (415)
    - txt extension with text/plain MIME (200 — accepted by REQ-1.1)
    - oversized file (413)
    - empty file (422)
    - malformed CSV / binary content (422)
    - missing required columns (422)
    - confirmation success (201)
    - expired/missing token (404)
    - validation-blocked confirmation (422)
    - conflict-blocked confirmation (409)

Uses the shared conftest fixtures (authed_client + db_session) which connect to the
test database.  The test database is seeded with 10 provinces and 10
indicators by setup_test_database.
"""

from __future__ import annotations

import asyncio
import io
import uuid

import pytest
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

# ---------------------------------------------------------------------------
# Seed indicators once for this test module (provinces already seeded by
# the shared conftest; categories seeded too).
# NOT autouse — only pulled in by tests that explicitly request it.
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def seed_indicators_for_import_tests():
    """Seed indicators into the test database once before import tests run."""
    from app.core.config import settings
    from app.db.seeders.indicators import seed_indicators

    async def _run():
        engine = create_async_engine(
            settings.TEST_DATABASE_URL, echo=False, future=True, poolclass=NullPool
        )
        factory = async_sessionmaker(
            bind=engine, expire_on_commit=False, autocommit=False, autoflush=False
        )
        async with factory() as session:
            await seed_indicators(session)
        await engine.dispose()

    asyncio.run(_run())
    yield


# ---------------------------------------------------------------------------
# CSV builders
# ---------------------------------------------------------------------------

HEADER = "province_code,indicator_code,value,reference_year,dataset_name,source_name\n"


def _valid_csv(
    province_code="CP", indicator_code="POVERTY_RATE", dataset="TestDS", source="Test Source"
) -> bytes:
    return (HEADER + f"{province_code},{indicator_code},55.2,2023,{dataset},{source}\n").encode()


def _csv_with_error(province_code="UNKNOWN_PROV") -> bytes:
    return (HEADER + f"{province_code},POVERTY_RATE,55.2,2023,TestDS,Test Source\n").encode()


def _missing_columns_csv() -> bytes:
    # missing 'value' column
    return b"province_code,indicator_code,reference_year,dataset_name,source_name\nCP,POVERTY_RATE,2023,DS,S\n"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _upload(content: bytes, filename: str = "test.csv"):
    return {"file": (filename, io.BytesIO(content), "text/csv")}


# ---------------------------------------------------------------------------
# Preview endpoint tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_preview_valid_csv_returns_200(authed_client):
    """A well-formed CSV with valid province and indicator returns HTTP 200."""
    resp = await authed_client.post(
        "/api/v1/imports/csv/preview",
        files=_upload(_valid_csv()),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "preview_token" in data
    assert data["total_rows"] >= 1
    assert "can_confirm" in data
    assert "errors" in data
    assert isinstance(data["sample_records"], list)


@pytest.mark.asyncio
async def test_preview_invalid_extension_returns_415(authed_client):
    # The endpoint checks MIME type, not file extension.
    # Sending a non-CSV MIME type triggers HTTP 415.
    resp = await authed_client.post(
        "/api/v1/imports/csv/preview",
        files={"file": ("data.xlsx", b"some,data\n1,2\n", "application/vnd.ms-excel")},
    )
    assert resp.status_code == 415


@pytest.mark.asyncio
async def test_preview_txt_extension_with_text_plain_mime_returns_200(authed_client):
    # REQ-1.1: text/plain MIME is accepted (even with a .txt filename).
    # The MIME type check passes; the content is valid CSV so 200 is expected.
    resp = await authed_client.post(
        "/api/v1/imports/csv/preview",
        files={"file": ("data.txt", _valid_csv(), "text/plain")},
    )
    assert resp.status_code == 200


@pytest.mark.asyncio
async def test_preview_oversized_file_returns_413(authed_client):
    big = b"x" * (5 * 1024 * 1024 + 1)
    resp = await authed_client.post(
        "/api/v1/imports/csv/preview",
        files=_upload(big),
    )
    assert resp.status_code == 413


@pytest.mark.asyncio
async def test_preview_empty_file_returns_422(authed_client):
    # REQ-1.3 / spec: empty files return HTTP 422 (not 400)
    resp = await authed_client.post(
        "/api/v1/imports/csv/preview",
        files=_upload(b""),
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_preview_binary_content_returns_422(authed_client):
    """Binary (non-UTF-8) bytes must be rejected with 422 (malformed CSV)."""
    binary = bytes(range(256))
    resp = await authed_client.post(
        "/api/v1/imports/csv/preview",
        files=_upload(binary),
    )
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_preview_missing_columns_returns_422(authed_client):
    # REQ-2.2 / spec: missing required columns return HTTP 422 (not 400)
    resp = await authed_client.post(
        "/api/v1/imports/csv/preview",
        files=_upload(_missing_columns_csv()),
    )
    assert resp.status_code == 422
    data = resp.json()
    # detail should mention the missing column name
    assert "value" in str(data["detail"]).lower() or "missing" in str(data["detail"]).lower()


@pytest.mark.asyncio
async def test_preview_unknown_province_returns_200_with_errors(authed_client):
    """
    A CSV with an unknown province_code is NOT a file-level error — it returns
    HTTP 200 with row-level errors and can_confirm=False.
    """
    resp = await authed_client.post(
        "/api/v1/imports/csv/preview",
        files=_upload(_csv_with_error("UNKNOWN_ZZZ")),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["can_confirm"] is False
    assert data["invalid_rows"] >= 1
    assert len(data["errors"]) >= 1


@pytest.mark.asyncio
async def test_inspect_csv_returns_200_and_inspection_token(authed_client):
    """File inspection returns metadata and an inspection token."""
    content = _valid_csv()
    resp = await authed_client.post(
        "/api/v1/imports/files/inspect",
        files=_upload(content),
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "inspection_token" in data
    assert data["inspection_token"].strip() != ""
    assert data["filename"] == "test.csv"
    assert data["source_format"] == "csv"
    assert data["direct_schema_match"] is True
    assert isinstance(data["columns"], list)
    assert len(data["columns"]) >= 5


@pytest.mark.asyncio
async def test_inspect_csv_duplicate_headers_returns_422(authed_client):
    csv_content = (
        b"province_code,province_code,value,reference_year,dataset_name\nCP,CP,1,2020,DS\n"
    )
    resp = await authed_client.post(
        "/api/v1/imports/files/inspect",
        files={"file": ("duplicate.csv", io.BytesIO(csv_content), "text/csv")},
    )
    assert resp.status_code == 422
    assert "duplicate" in resp.text.lower()


@pytest.mark.asyncio
async def test_inspect_csv_invalid_mime_returns_415(authed_client):
    content = _valid_csv()
    resp = await authed_client.post(
        "/api/v1/imports/files/inspect",
        files={"file": ("test.csv", io.BytesIO(content), "application/octet-stream")},
    )
    assert resp.status_code == 415


@pytest.mark.asyncio
async def test_inspect_txt_file_with_text_plain_mime_returns_200(authed_client):
    content = _valid_csv()
    resp = await authed_client.post(
        "/api/v1/imports/files/inspect",
        files={"file": ("test.txt", io.BytesIO(content), "text/plain")},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["source_format"] == "csv"
    assert data["direct_schema_match"] is True
    assert len(data["suggested_mappings"]) == 5


@pytest.mark.asyncio
async def test_create_import_template_and_list_templates(authed_client):
    content = _valid_csv()
    inspect_resp = await authed_client.post(
        "/api/v1/imports/files/inspect",
        files={"file": ("test.csv", io.BytesIO(content), "text/csv")},
    )
    assert inspect_resp.status_code == 200
    inspection_data = inspect_resp.json()

    payload = {
        "name": "Canonical CSV Mapping",
        "description": "Template for canonical StatFlow CSV files.",
        "source_format": inspection_data["source_format"],
        "original_headers": inspection_data["headers"],
        "mapping_config": {
            "mapping_version": 1,
            "mappings": inspection_data["suggested_mappings"],
        },
    }

    create_resp = await authed_client.post(
        "/api/v1/imports/templates",
        json=payload,
    )
    assert create_resp.status_code == 201, create_resp.text
    template = create_resp.json()
    assert template["name"] == payload["name"]
    assert template["source_format"] == payload["source_format"]
    assert template["original_headers"] == payload["original_headers"]

    list_resp = await authed_client.get("/api/v1/imports/templates")
    assert list_resp.status_code == 200
    list_data = list_resp.json()
    assert any(t["name"] == payload["name"] for t in list_data["templates"])

    # GET by id
    get_resp = await authed_client.get(f"/api/v1/imports/templates/{template['id']}")
    assert get_resp.status_code == 200
    got = get_resp.json()
    assert got["id"] == template["id"]
    assert got["name"] == payload["name"]

    # PATCH update
    update_payload = {
        "name": "Updated CSV Mapping",
        "description": "Updated description.",
    }
    patch_resp = await authed_client.patch(
        f"/api/v1/imports/templates/{template['id']}",
        json=update_payload,
    )
    assert patch_resp.status_code == 200
    updated = patch_resp.json()
    assert updated["name"] == update_payload["name"]
    assert updated["description"] == update_payload["description"]

    # DELETE the template and verify it is no longer returned in the active list
    delete_resp = await authed_client.delete(f"/api/v1/imports/templates/{template['id']}")
    assert delete_resp.status_code == 204

    list_after_delete_resp = await authed_client.get("/api/v1/imports/templates")
    assert list_after_delete_resp.status_code == 200
    list_after_delete_data = list_after_delete_resp.json()
    assert not any(t["id"] == template["id"] for t in list_after_delete_data["templates"])


# ---------------------------------------------------------------------------
# Confirm endpoint tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_confirm_missing_token_returns_404(authed_client):
    resp = await authed_client.post(
        "/api/v1/imports/csv/confirm",
        json={"preview_token": str(uuid.uuid4())},
    )
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_confirm_validation_errors_blocked_returns_422(authed_client):
    """
    A preview that has row-level errors must be blocked at confirm with 422.
    """
    # Preview a CSV with an unknown province (produces row errors)
    prev_resp = await authed_client.post(
        "/api/v1/imports/csv/preview",
        files=_upload(_csv_with_error("UNKNOWN_ZZZ")),
    )
    assert prev_resp.status_code == 200
    token = prev_resp.json()["preview_token"]

    confirm_resp = await authed_client.post(
        "/api/v1/imports/csv/confirm",
        json={"preview_token": token},
    )
    assert confirm_resp.status_code == 422


@pytest.mark.asyncio
async def test_confirm_success_returns_201(
    authed_client, db_session, seed_indicators_for_import_tests
):
    """
    A fully valid preview should confirm successfully with HTTP 201.
    We use seeded province CP and indicator POVERTY_RATE from the test DB.
    """
    # First get a valid province code and indicator code from the test DB
    from app.models.indicator import Indicator
    from app.models.province import Province
    from sqlalchemy import select

    prov_result = await db_session.execute(select(Province).limit(1))
    prov = prov_result.scalars().first()
    if prov is None:
        pytest.skip("No provinces in test database")

    ind_result = await db_session.execute(select(Indicator).limit(1))
    ind = ind_result.scalars().first()
    if ind is None:
        pytest.skip("No indicators in test database")

    # Use a unique dataset name to avoid conflicts with other tests
    ds_name = f"IntegTestDS_{uuid.uuid4().hex[:8]}"
    csv_content = (
        f"province_code,indicator_code,value,reference_year,dataset_name,source_name\n"
        f"{prov.code},{ind.code},42.5,2020,{ds_name},Integration Test Source\n"
    ).encode()

    prev_resp = await authed_client.post(
        "/api/v1/imports/csv/preview",
        files=_upload(csv_content),
    )
    assert prev_resp.status_code == 200, prev_resp.text
    preview = prev_resp.json()
    assert preview["can_confirm"] is True, f"Preview not clean: {preview}"

    confirm_resp = await authed_client.post(
        "/api/v1/imports/csv/confirm",
        json={"preview_token": preview["preview_token"]},
    )
    assert confirm_resp.status_code == 201, confirm_resp.text
    result = confirm_resp.json()
    assert result["imported_count"] == 1
    assert result["datasets_created"] == 1
    assert len(result["dataset_ids"]) == 1

    # Token must be consumed — second confirm attempt returns 404
    second_resp = await authed_client.post(
        "/api/v1/imports/csv/confirm",
        json={"preview_token": preview["preview_token"]},
    )
    assert second_resp.status_code == 404


@pytest.mark.asyncio
async def test_confirm_conflict_returns_409(
    authed_client, db_session, seed_indicators_for_import_tests
):
    """
    Import the same row twice: first import succeeds; second preview
    detects a conflict and confirm returns 409.
    """
    from app.models.indicator import Indicator
    from app.models.province import Province
    from sqlalchemy import select

    prov_result = await db_session.execute(select(Province).limit(1))
    prov = prov_result.scalars().first()
    if prov is None:
        pytest.skip("No provinces in test database")

    ind_result = await db_session.execute(select(Indicator).limit(1))
    ind = ind_result.scalars().first()
    if ind is None:
        pytest.skip("No indicators in test database")

    ds_name = f"ConflictTestDS_{uuid.uuid4().hex[:8]}"
    csv_content = (
        f"province_code,indicator_code,value,reference_year,dataset_name,source_name\n"
        f"{prov.code},{ind.code},99.9,2021,{ds_name},Conflict Test Source\n"
    ).encode()

    # First import — should succeed
    prev1 = await authed_client.post("/api/v1/imports/csv/preview", files=_upload(csv_content))
    assert prev1.status_code == 200
    assert prev1.json()["can_confirm"] is True

    conf1 = await authed_client.post(
        "/api/v1/imports/csv/confirm",
        json={"preview_token": prev1.json()["preview_token"]},
    )
    assert conf1.status_code == 201

    # Second preview of identical data — must detect conflict
    prev2 = await authed_client.post("/api/v1/imports/csv/preview", files=_upload(csv_content))
    assert prev2.status_code == 200
    preview2 = prev2.json()
    assert preview2["conflict_rows"] >= 1
    assert preview2["can_confirm"] is False

    # Confirm with a conflicted token must return 409
    conf2 = await authed_client.post(
        "/api/v1/imports/csv/confirm",
        json={"preview_token": preview2["preview_token"]},
    )
    assert conf2.status_code == 409
