import hashlib
import json
import uuid

import pytest
from app.models.universal_dataset import (
    UniversalDataset,
    UniversalDatasetColumn,
    UniversalDatasetRow,
    UniversalDatasetVersion,
)
from app.models.user import User, UserRole
from app.services.universal_dataset_persistence_service import (
    UniversalDatasetPersistenceService,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


async def _create_owner(db_session: AsyncSession) -> User:
    owner = User(
        email=f"owner-{uuid.uuid4().hex[:8]}@example.com",
        hashed_password="hashed",
        full_name="Owner",
        role=UserRole.ADMIN,
        is_active=True,
    )
    db_session.add(owner)
    await db_session.flush()
    return owner


async def test_create_dataset_from_rows_persists_dataset_version_columns_and_rows(
    db_session: AsyncSession,
) -> None:
    owner = await _create_owner(db_session)
    service = UniversalDatasetPersistenceService(db_session)

    rows = [
        {"province_code": "A01", "value": 123.45},
        {"province_code": "B02", "value": 67.8, "label": "second"},
    ]

    dataset = await service.create_dataset_from_rows(
        owner_id=owner.id,
        name="Sales Data",
        description="Sales rows",
        source_filename="sales.csv",
        rows=rows,
    )

    assert isinstance(dataset, UniversalDataset)
    assert dataset.name == "Sales Data"
    assert dataset.owner_id == owner.id
    assert dataset.current_version_id is not None

    version = await db_session.get(UniversalDatasetVersion, dataset.current_version_id)
    assert version is not None
    assert version.version_number == 1
    assert version.row_count == 2
    assert version.column_count == 3

    columns_result = await db_session.execute(
        select(UniversalDatasetColumn).where(
            UniversalDatasetColumn.dataset_version_id == version.id
        )
    )
    columns = columns_result.scalars().all()
    assert len(columns) == 3

    column_names = [column.name for column in columns]
    assert column_names[0] == "province_code"
    assert column_names[1] == "value"
    assert column_names[2] == "label"

    persisted_rows_result = await db_session.execute(
        select(UniversalDatasetRow)
        .where(UniversalDatasetRow.dataset_version_id == version.id)
        .order_by(UniversalDatasetRow.row_number)
    )
    persisted_rows = persisted_rows_result.scalars().all()
    assert len(persisted_rows) == 2
    assert persisted_rows[0].row_number == 1
    assert persisted_rows[1].row_number == 2
    assert persisted_rows[0].data_json == {"province_code": "A01", "value": 123.45, "label": None}
    assert persisted_rows[1].data_json == {"province_code": "B02", "value": 67.8, "label": "second"}


async def test_create_dataset_from_rows_rejects_empty_name(db_session: AsyncSession) -> None:
    owner = await _create_owner(db_session)
    service = UniversalDatasetPersistenceService(db_session)

    with pytest.raises(ValueError, match="Dataset name cannot be empty"):
        await service.create_dataset_from_rows(
            owner_id=owner.id,
            name="   ",
            description=None,
            source_filename="sales.csv",
            rows=[{"value": 1}],
        )


async def test_create_dataset_from_rows_rejects_empty_rows(db_session: AsyncSession) -> None:
    owner = await _create_owner(db_session)
    service = UniversalDatasetPersistenceService(db_session)

    with pytest.raises(ValueError, match="Rows list cannot be empty"):
        await service.create_dataset_from_rows(
            owner_id=owner.id,
            name="Sales",
            description=None,
            source_filename="sales.csv",
            rows=[],
        )


async def test_create_dataset_from_rows_uses_deterministic_row_hashes_and_row_numbers(
    db_session: AsyncSession,
) -> None:
    owner = await _create_owner(db_session)
    service = UniversalDatasetPersistenceService(db_session)

    rows = [{"value": 3}, {"value": 4}]
    dataset = await service.create_dataset_from_rows(
        owner_id=owner.id,
        name="Hash Rows",
        description=None,
        source_filename="hash.csv",
        rows=rows,
    )

    version = await db_session.get(UniversalDatasetVersion, dataset.current_version_id)
    persisted_rows_result = await db_session.execute(
        select(UniversalDatasetRow)
        .where(UniversalDatasetRow.dataset_version_id == version.id)
        .order_by(UniversalDatasetRow.row_number)
    )
    persisted_rows = persisted_rows_result.scalars().all()

    for row_obj in persisted_rows:
        normalized = json.dumps(
            row_obj.data_json, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        )
        expected_hash = hashlib.sha256(normalized.encode("utf-8")).hexdigest()
        assert row_obj.row_hash == expected_hash

    assert [row.row_number for row in persisted_rows] == [1, 2]


async def test_create_dataset_from_rows_rolls_back_on_row_failure(db_session: AsyncSession) -> None:
    owner = await _create_owner(db_session)
    service = UniversalDatasetPersistenceService(db_session)

    rows = [{"value": 1}, ["not a mapping"]]

    with pytest.raises(ValueError):
        await service.create_dataset_from_rows(
            owner_id=owner.id,
            name="Rollback Rows",
            description=None,
            source_filename="rollback.csv",
            rows=rows,
        )

    count_result = await db_session.execute(select(UniversalDataset))
    count = len(count_result.scalars().all())
    assert count == 0


async def test_create_dataset_from_rows_rolls_back_on_column_failure(
    db_session: AsyncSession,
) -> None:
    owner = await _create_owner(db_session)
    service = UniversalDatasetPersistenceService(db_session)

    rows = [{1: "bad"}]

    with pytest.raises(ValueError):
        await service.create_dataset_from_rows(
            owner_id=owner.id,
            name="Rollback Columns",
            description=None,
            source_filename="rollback.csv",
            rows=rows,
        )

    count_result = await db_session.execute(select(UniversalDataset))
    count = len(count_result.scalars().all())
    assert count == 0


async def test_create_dataset_from_rows_stores_owner_and_version_metadata(
    db_session: AsyncSession,
) -> None:
    owner = await _create_owner(db_session)
    service = UniversalDatasetPersistenceService(db_session)

    dataset = await service.create_dataset_from_rows(
        owner_id=owner.id,
        name="Owner Data",
        description="owner",
        source_filename="owner.csv",
        rows=[{"value": 1}],
    )

    assert dataset.owner_id == owner.id
    version = await db_session.get(UniversalDatasetVersion, dataset.current_version_id)
    assert version is not None
    assert version.source_type == "csv"
    assert version.schema_json["columns"] == ["value"]
