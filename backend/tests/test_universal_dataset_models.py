import hashlib
import json

import pytest
from app.models.universal_dataset import (
    UniversalDataset,
    UniversalDatasetColumn,
    UniversalDatasetRow,
    UniversalDatasetVersion,
)
from app.models.user import User, UserRole
from sqlalchemy.exc import IntegrityError


async def test_universal_dataset_models_persist_with_relationships(db_session) -> None:
    owner = User(
        email="universal-owner@example.com",
        hashed_password="hashed",
        full_name="Universal Owner",
        role=UserRole.ADMIN,
        is_active=True,
    )
    db_session.add(owner)
    await db_session.flush()

    dataset = UniversalDataset(
        owner_id=owner.id,
        name="Sales Snapshot",
        description="Universal dataset for sales data",
        source_filename="sales.csv",
        status="draft",
    )
    db_session.add(dataset)
    await db_session.flush()

    version = UniversalDatasetVersion(
        dataset_id=dataset.id,
        version_number=1,
        row_count=120,
        column_count=5,
        schema_json={"columns": ["province_code", "indicator_code", "value"]},
        source_type="csv",
    )
    db_session.add(version)
    await db_session.flush()

    column = UniversalDatasetColumn(
        dataset_version_id=version.id,
        name="revenue",
        original_name="Revenue",
        inferred_type="DECIMAL",
        semantic_type="metric",
        ordinal_position=0,
        nullable=False,
        metadata_json={"description": "Revenue in local currency"},
    )
    db_session.add(column)
    await db_session.flush()

    await db_session.refresh(dataset)
    await db_session.refresh(version)
    await db_session.refresh(column)

    assert dataset.owner_id == owner.id
    assert dataset.current_version_id is None
    versions_count = await db_session.run_sync(lambda session: len(dataset.versions))
    columns_count = await db_session.run_sync(lambda session: len(version.columns))
    assert versions_count == 1
    assert version.dataset_id == dataset.id
    assert columns_count == 1
    assert await db_session.run_sync(lambda session: version.columns[0].name) == "revenue"


async def test_universal_dataset_row_models_persist_with_relationships(db_session) -> None:
    owner = User(
        email="row-owner@example.com",
        hashed_password="hashed",
        full_name="Row Owner",
        role=UserRole.ADMIN,
        is_active=True,
    )
    db_session.add(owner)
    await db_session.flush()

    dataset = UniversalDataset(
        owner_id=owner.id, name="Rows Dataset", source_filename="rows.csv", status="draft"
    )
    db_session.add(dataset)
    await db_session.flush()

    version = UniversalDatasetVersion(
        dataset_id=dataset.id,
        version_number=1,
        row_count=1,
        column_count=2,
        schema_json={"columns": ["province_code", "value"]},
        source_type="csv",
    )
    db_session.add(version)
    await db_session.flush()

    row_payload = {"province_code": "A01", "value": 123.45}
    row = UniversalDatasetRow(
        dataset_version_id=version.id,
        row_number=1,
        data_json=row_payload,
    )
    db_session.add(row)
    await db_session.flush()

    await db_session.refresh(version)
    await db_session.refresh(row)

    normalized = json.dumps(row_payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    expected_hash = hashlib.sha256(normalized.encode("utf-8")).hexdigest()

    assert row.dataset_version_id == version.id
    assert row.row_number == 1
    assert row.row_hash == expected_hash
    rows_count = await db_session.run_sync(lambda session: len(version.rows))
    assert rows_count == 1


async def test_version_number_is_unique_per_dataset(db_session) -> None:
    owner = User(
        email="version-owner@example.com",
        hashed_password="hashed",
        full_name="Version Owner",
        role=UserRole.ADMIN,
        is_active=True,
    )
    db_session.add(owner)
    await db_session.flush()

    dataset = UniversalDataset(
        owner_id=owner.id,
        name="Duplicate Version Dataset",
        source_filename="dup.csv",
        status="draft",
    )
    db_session.add(dataset)
    await db_session.flush()

    first = UniversalDatasetVersion(
        dataset_id=dataset.id,
        version_number=1,
        row_count=1,
        column_count=1,
        schema_json={"columns": []},
        source_type="csv",
    )
    second = UniversalDatasetVersion(
        dataset_id=dataset.id,
        version_number=1,
        row_count=2,
        column_count=2,
        schema_json={"columns": []},
        source_type="csv",
    )
    db_session.add_all([first, second])

    with pytest.raises(IntegrityError):
        await db_session.flush()

    await db_session.rollback()


async def test_row_number_is_unique_per_dataset_version(db_session) -> None:
    owner = User(
        email="row-number-owner@example.com",
        hashed_password="hashed",
        full_name="Row Number Owner",
        role=UserRole.ADMIN,
        is_active=True,
    )
    db_session.add(owner)
    await db_session.flush()

    dataset = UniversalDataset(
        owner_id=owner.id,
        name="Duplicate Row Number Dataset",
        source_filename="rows.csv",
        status="draft",
    )
    db_session.add(dataset)
    await db_session.flush()

    version = UniversalDatasetVersion(
        dataset_id=dataset.id,
        version_number=1,
        row_count=2,
        column_count=1,
        schema_json={"columns": ["value"]},
        source_type="csv",
    )
    db_session.add(version)
    await db_session.flush()

    first = UniversalDatasetRow(dataset_version_id=version.id, row_number=1, data_json={"value": 1})
    second = UniversalDatasetRow(
        dataset_version_id=version.id, row_number=1, data_json={"value": 2}
    )
    db_session.add_all([first, second])

    with pytest.raises(IntegrityError):
        await db_session.flush()

    await db_session.rollback()


async def test_column_name_is_unique_per_dataset_version(db_session) -> None:
    owner = User(
        email="column-owner@example.com",
        hashed_password="hashed",
        full_name="Column Owner",
        role=UserRole.ADMIN,
        is_active=True,
    )
    db_session.add(owner)
    await db_session.flush()

    dataset = UniversalDataset(
        owner_id=owner.id,
        name="Duplicate Column Dataset",
        source_filename="columns.csv",
        status="draft",
    )
    db_session.add(dataset)
    await db_session.flush()

    version = UniversalDatasetVersion(
        dataset_id=dataset.id,
        version_number=1,
        row_count=3,
        column_count=3,
        schema_json={"columns": []},
        source_type="csv",
    )
    db_session.add(version)
    await db_session.flush()

    first = UniversalDatasetColumn(
        dataset_version_id=version.id,
        name="value",
        original_name="Value",
        inferred_type="DECIMAL",
        ordinal_position=0,
        nullable=False,
    )
    second = UniversalDatasetColumn(
        dataset_version_id=version.id,
        name="value",
        original_name="Value 2",
        inferred_type="DECIMAL",
        ordinal_position=1,
        nullable=False,
    )
    db_session.add_all([first, second])

    with pytest.raises(IntegrityError):
        await db_session.flush()

    await db_session.rollback()
