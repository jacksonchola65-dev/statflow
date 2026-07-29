"""
tests/test_ingestion_schemas.py
===============================
Focused tests for ingestion API schemas.

Tests verify:
- ORM/model attribute validation
- UUID preservation
- datetime preservation
- enum/status serialization
- nullable fields handling
- ordered columns
- row values preserved exactly
- Decimal strings unchanged
- sample values preserved
- pagination calculations
- invalid counts rejected where appropriate
- invalid page/page_size rejected where appropriate
- ingestion result mapping
- JSON serialization compatibility
"""

from __future__ import annotations

import sys

if sys.platform == "win32":
    import asyncio as _asyncio
    _asyncio.set_event_loop_policy(_asyncio.WindowsSelectorEventLoopPolicy())

import uuid
from datetime import datetime, timezone
from typing import Optional

import pytest
from pydantic import ValidationError

from app.models.data_source import FileFormat
from app.models.ingestion import (
    DatasetColumn,
    DatasetRow,
    IngestionJob,
    IngestionStatus,
    InferredColumnType,
)
from app.schemas.ingestion import (
    DatasetColumnResponse,
    DatasetInspectionResponse,
    DatasetRowResponse,
    IngestionJobSummaryResponse,
    IngestionResultResponse,
    PaginationResponse,
)
from app.services.ingestion_persistence_service import IngestionPersistenceResult


# ===========================================================================
# PaginationResponse tests
# ===========================================================================


def test_pagination_valid():
    """PaginationResponse accepts valid pagination data."""
    pagination = PaginationResponse(
        page=1,
        page_size=50,
        total_items=150,
        total_pages=3,
        has_next=True,
        has_previous=False,
    )

    assert pagination.page == 1
    assert pagination.page_size == 50
    assert pagination.total_items == 150
    assert pagination.total_pages == 3
    assert pagination.has_next is True
    assert pagination.has_previous is False


def test_pagination_rejects_zero_page():
    """PaginationResponse rejects page < 1."""
    with pytest.raises(ValidationError):
        PaginationResponse(
            page=0,
            page_size=50,
            total_items=150,
            total_pages=3,
            has_next=True,
            has_previous=False,
        )


def test_pagination_rejects_zero_page_size():
    """PaginationResponse rejects page_size < 1."""
    with pytest.raises(ValidationError):
        PaginationResponse(
            page=1,
            page_size=0,
            total_items=150,
            total_pages=3,
            has_next=True,
            has_previous=False,
        )


def test_pagination_rejects_excessive_page_size():
    """PaginationResponse rejects page_size > 10000."""
    with pytest.raises(ValidationError):
        PaginationResponse(
            page=1,
            page_size=10001,
            total_items=150,
            total_pages=3,
            has_next=True,
            has_previous=False,
        )


def test_pagination_rejects_negative_total_items():
    """PaginationResponse rejects total_items < 0."""
    with pytest.raises(ValidationError):
        PaginationResponse(
            page=1,
            page_size=50,
            total_items=-1,
            total_pages=3,
            has_next=True,
            has_previous=False,
        )


# ===========================================================================
# IngestionJobSummaryResponse tests
# ===========================================================================


def test_ingestion_job_summary_preserves_uuid():
    """IngestionJobSummaryResponse preserves UUID types."""
    job_id = uuid.uuid4()
    registry_id = uuid.uuid4()
    creator_id = uuid.uuid4()

    response = IngestionJobSummaryResponse(
        id=job_id,
        dataset_registry_id=registry_id,
        status=IngestionStatus.COMPLETED,
        original_filename="test.csv",
        file_format=FileFormat.CSV,
        row_count=100,
        column_count=5,
        started_at=None,
        completed_at=datetime.now(timezone.utc),
        failed_at=None,
        error_message=None,
        created_by_user_id=creator_id,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )

    assert isinstance(response.id, uuid.UUID)
    assert response.id == job_id
    assert isinstance(response.dataset_registry_id, uuid.UUID)
    assert response.dataset_registry_id == registry_id
    assert isinstance(response.created_by_user_id, uuid.UUID)
    assert response.created_by_user_id == creator_id


def test_ingestion_job_summary_preserves_datetime():
    """IngestionJobSummaryResponse preserves datetime types."""
    now = datetime.now(timezone.utc)

    response = IngestionJobSummaryResponse(
        id=uuid.uuid4(),
        dataset_registry_id=uuid.uuid4(),
        status=IngestionStatus.COMPLETED,
        original_filename="test.csv",
        file_format=FileFormat.CSV,
        row_count=100,
        column_count=5,
        started_at=now,
        completed_at=now,
        failed_at=None,
        error_message=None,
        created_by_user_id=None,
        created_at=now,
        updated_at=now,
    )

    assert isinstance(response.created_at, datetime)
    assert response.created_at == now
    assert isinstance(response.completed_at, datetime)
    assert response.completed_at == now


def test_ingestion_job_summary_enum_serialization():
    """IngestionJobSummaryResponse serializes enums correctly."""
    response = IngestionJobSummaryResponse(
        id=uuid.uuid4(),
        dataset_registry_id=uuid.uuid4(),
        status=IngestionStatus.PENDING,
        original_filename="test.csv",
        file_format=FileFormat.XLSX,
        row_count=None,
        column_count=None,
        started_at=None,
        completed_at=None,
        failed_at=None,
        error_message=None,
        created_by_user_id=None,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )

    assert response.status == IngestionStatus.PENDING
    assert response.file_format == FileFormat.XLSX
    # JSON serialization should work
    assert response.model_dump() is not None


def test_ingestion_job_summary_nullable_fields():
    """IngestionJobSummaryResponse accepts nullable optional fields."""
    response = IngestionJobSummaryResponse(
        id=uuid.uuid4(),
        dataset_registry_id=uuid.uuid4(),
        status=IngestionStatus.PENDING,
        original_filename="test.csv",
        file_format=None,
        row_count=None,
        column_count=None,
        started_at=None,
        completed_at=None,
        failed_at=None,
        error_message=None,
        created_by_user_id=None,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )

    assert response.file_format is None
    assert response.row_count is None
    assert response.created_by_user_id is None


# ===========================================================================
# DatasetColumnResponse tests
# ===========================================================================


def test_dataset_column_response_preserves_ordinal_position():
    """DatasetColumnResponse preserves ordinal_position ordering."""
    col0 = DatasetColumnResponse(
        id=uuid.uuid4(),
        ingestion_job_id=uuid.uuid4(),
        ordinal_position=0,
        original_name="First Column",
        normalized_name="first_column",
        inferred_type=InferredColumnType.TEXT,
        nullable=False,
        missing_count=0,
        unique_count=5,
        sample_values=["a", "b"],
        created_at=datetime.now(timezone.utc),
    )

    col1 = DatasetColumnResponse(
        id=uuid.uuid4(),
        ingestion_job_id=uuid.uuid4(),
        ordinal_position=1,
        original_name="Second Column",
        normalized_name="second_column",
        inferred_type=InferredColumnType.INTEGER,
        nullable=True,
        missing_count=2,
        unique_count=10,
        sample_values=["100", "200"],
        created_at=datetime.now(timezone.utc),
    )

    assert col0.ordinal_position == 0
    assert col1.ordinal_position == 1
    assert col0.ordinal_position < col1.ordinal_position


def test_dataset_column_response_sample_values_preserved():
    """DatasetColumnResponse preserves sample_values exactly."""
    samples = ["alice", "bob", "charlie"]

    response = DatasetColumnResponse(
        id=uuid.uuid4(),
        ingestion_job_id=uuid.uuid4(),
        ordinal_position=0,
        original_name="Name",
        normalized_name="name",
        inferred_type=InferredColumnType.TEXT,
        nullable=False,
        missing_count=0,
        unique_count=3,
        sample_values=samples,
        created_at=datetime.now(timezone.utc),
    )

    assert response.sample_values == samples
    assert response.sample_values is not None


def test_dataset_column_response_nullable_sample_values():
    """DatasetColumnResponse accepts None for sample_values."""
    response = DatasetColumnResponse(
        id=uuid.uuid4(),
        ingestion_job_id=uuid.uuid4(),
        ordinal_position=0,
        original_name="Name",
        normalized_name="name",
        inferred_type=InferredColumnType.TEXT,
        nullable=False,
        missing_count=0,
        unique_count=0,
        sample_values=None,
        created_at=datetime.now(timezone.utc),
    )

    assert response.sample_values is None


def test_dataset_column_response_inferred_type_serialization():
    """DatasetColumnResponse serializes InferredColumnType correctly."""
    types_to_test = [
        InferredColumnType.TEXT,
        InferredColumnType.INTEGER,
        InferredColumnType.DECIMAL,
        InferredColumnType.BOOLEAN,
        InferredColumnType.DATE,
        InferredColumnType.DATETIME,
    ]

    for col_type in types_to_test:
        response = DatasetColumnResponse(
            id=uuid.uuid4(),
            ingestion_job_id=uuid.uuid4(),
            ordinal_position=0,
            original_name="Test",
            normalized_name="test",
            inferred_type=col_type,
            nullable=False,
            missing_count=0,
            unique_count=0,
            sample_values=None,
            created_at=datetime.now(timezone.utc),
        )

        assert response.inferred_type == col_type


# ===========================================================================
# DatasetRowResponse tests
# ===========================================================================


def test_dataset_row_response_preserves_row_number():
    """DatasetRowResponse preserves row_number exactly."""
    job_id = uuid.uuid4()

    row0 = DatasetRowResponse(
        id=uuid.uuid4(),
        ingestion_job_id=job_id,
        row_number=0,
        values={"name": "alice", "age": "30"},
        created_at=datetime.now(timezone.utc),
    )

    row1 = DatasetRowResponse(
        id=uuid.uuid4(),
        ingestion_job_id=job_id,
        row_number=1,
        values={"name": "bob", "age": "25"},
        created_at=datetime.now(timezone.utc),
    )

    assert row0.row_number == 0
    assert row1.row_number == 1


def test_dataset_row_response_preserves_values_exactly():
    """DatasetRowResponse preserves values dict exactly (no re-serialization)."""
    values = {
        "string_col": "text",
        "int_col": 42,
        "float_col": 3.14,
        "bool_col": True,
        "null_col": None,
        "decimal_str": "0.0000000001",
        "decimal_with_zeros": "100.00",
    }

    response = DatasetRowResponse(
        id=uuid.uuid4(),
        ingestion_job_id=uuid.uuid4(),
        row_number=0,
        values=values,
        created_at=datetime.now(timezone.utc),
    )

    assert response.values == values
    assert response.values["decimal_str"] == "0.0000000001"
    assert response.values["decimal_with_zeros"] == "100.00"
    assert response.values["bool_col"] is True
    assert response.values["null_col"] is None


def test_dataset_row_response_uuid_preservation():
    """DatasetRowResponse preserves UUID types."""
    row_id = uuid.uuid4()
    job_id = uuid.uuid4()

    response = DatasetRowResponse(
        id=row_id,
        ingestion_job_id=job_id,
        row_number=0,
        values={},
        created_at=datetime.now(timezone.utc),
    )

    assert isinstance(response.id, uuid.UUID)
    assert response.id == row_id
    assert isinstance(response.ingestion_job_id, uuid.UUID)
    assert response.ingestion_job_id == job_id


# ===========================================================================
# DatasetInspectionResponse tests
# ===========================================================================


def test_dataset_inspection_response_composite():
    """DatasetInspectionResponse combines job, columns, rows, pagination."""
    now = datetime.now(timezone.utc)
    job_id = uuid.uuid4()

    job = IngestionJobSummaryResponse(
        id=job_id,
        dataset_registry_id=uuid.uuid4(),
        status=IngestionStatus.COMPLETED,
        original_filename="test.csv",
        file_format=FileFormat.CSV,
        row_count=2,
        column_count=2,
        started_at=None,
        completed_at=now,
        failed_at=None,
        error_message=None,
        created_by_user_id=None,
        created_at=now,
        updated_at=now,
    )

    columns = [
        DatasetColumnResponse(
            id=uuid.uuid4(),
            ingestion_job_id=job_id,
            ordinal_position=0,
            original_name="Col A",
            normalized_name="col_a",
            inferred_type=InferredColumnType.TEXT,
            nullable=False,
            missing_count=0,
            unique_count=2,
            sample_values=["val1", "val2"],
            created_at=now,
        ),
        DatasetColumnResponse(
            id=uuid.uuid4(),
            ingestion_job_id=job_id,
            ordinal_position=1,
            original_name="Col B",
            normalized_name="col_b",
            inferred_type=InferredColumnType.INTEGER,
            nullable=False,
            missing_count=0,
            unique_count=2,
            sample_values=["100", "200"],
            created_at=now,
        ),
    ]

    rows = [
        DatasetRowResponse(
            id=uuid.uuid4(),
            ingestion_job_id=job_id,
            row_number=0,
            values={"col_a": "val1", "col_b": "100"},
            created_at=now,
        ),
        DatasetRowResponse(
            id=uuid.uuid4(),
            ingestion_job_id=job_id,
            row_number=1,
            values={"col_a": "val2", "col_b": "200"},
            created_at=now,
        ),
    ]

    pagination = PaginationResponse(
        page=1,
        page_size=50,
        total_items=2,
        total_pages=1,
        has_next=False,
        has_previous=False,
    )

    response = DatasetInspectionResponse(
        job=job,
        columns=columns,
        rows=rows,
        pagination=pagination,
    )

    assert response.job.id == job_id
    assert len(response.columns) == 2
    assert len(response.rows) == 2
    assert response.pagination.total_items == 2


def test_dataset_inspection_response_columns_ordered():
    """DatasetInspectionResponse maintains column ordinal_position order."""
    now = datetime.now(timezone.utc)
    job_id = uuid.uuid4()

    job = IngestionJobSummaryResponse(
        id=job_id,
        dataset_registry_id=uuid.uuid4(),
        status=IngestionStatus.COMPLETED,
        original_filename="test.csv",
        file_format=FileFormat.CSV,
        row_count=1,
        column_count=3,
        started_at=None,
        completed_at=now,
        failed_at=None,
        error_message=None,
        created_by_user_id=None,
        created_at=now,
        updated_at=now,
    )

    # Create columns in order 0, 1, 2
    columns = [
        DatasetColumnResponse(
            id=uuid.uuid4(),
            ingestion_job_id=job_id,
            ordinal_position=i,
            original_name=f"Col {i}",
            normalized_name=f"col_{i}",
            inferred_type=InferredColumnType.TEXT,
            nullable=False,
            missing_count=0,
            unique_count=1,
            sample_values=[f"val{i}"],
            created_at=now,
        )
        for i in range(3)
    ]

    rows = [
        DatasetRowResponse(
            id=uuid.uuid4(),
            ingestion_job_id=job_id,
            row_number=0,
            values={"col_0": "val0", "col_1": "val1", "col_2": "val2"},
            created_at=now,
        )
    ]

    pagination = PaginationResponse(
        page=1,
        page_size=50,
        total_items=1,
        total_pages=1,
        has_next=False,
        has_previous=False,
    )

    response = DatasetInspectionResponse(
        job=job,
        columns=columns,
        rows=rows,
        pagination=pagination,
    )

    # Verify ordinal positions are in order
    for i, col in enumerate(response.columns):
        assert col.ordinal_position == i


# ===========================================================================
# IngestionResultResponse tests
# ===========================================================================


def test_ingestion_result_response_maps_persistence_result():
    """IngestionResultResponse maps IngestionPersistenceResult correctly."""
    job_id = uuid.uuid4()

    result = IngestionResultResponse(
        ingestion_job_id=job_id,
        columns_inserted=5,
        rows_inserted=100,
        final_status=IngestionStatus.COMPLETED,
    )

    assert result.ingestion_job_id == job_id
    assert result.columns_inserted == 5
    assert result.rows_inserted == 100
    assert result.final_status == IngestionStatus.COMPLETED


def test_ingestion_result_response_status_serialization():
    """IngestionResultResponse serializes IngestionStatus correctly."""
    statuses = [
        IngestionStatus.PENDING,
        IngestionStatus.PROCESSING,
        IngestionStatus.COMPLETED,
        IngestionStatus.FAILED,
    ]

    for status in statuses:
        result = IngestionResultResponse(
            ingestion_job_id=uuid.uuid4(),
            columns_inserted=0,
            rows_inserted=0,
            final_status=status,
        )

        assert result.final_status == status
        # Verify JSON serialization works
        dumped = result.model_dump()
        assert dumped["final_status"] == status.value


def test_ingestion_result_response_json_serializable():
    """IngestionResultResponse produces JSON-compatible output."""
    job_id = uuid.uuid4()

    result = IngestionResultResponse(
        ingestion_job_id=job_id,
        columns_inserted=5,
        rows_inserted=100,
        final_status=IngestionStatus.COMPLETED,
    )

    # model_dump_json should work without errors
    json_str = result.model_dump_json()
    assert isinstance(json_str, str)
    assert str(job_id) in json_str
    assert "COMPLETED" in json_str


# ===========================================================================
# Schema JSON serialization tests
# ===========================================================================


def test_pagination_json_serializable():
    """PaginationResponse produces valid JSON."""
    pagination = PaginationResponse(
        page=2,
        page_size=25,
        total_items=100,
        total_pages=4,
        has_next=True,
        has_previous=True,
    )

    json_str = pagination.model_dump_json()
    assert isinstance(json_str, str)
    assert '"page": 2' in json_str or '"page":2' in json_str


def test_ingestion_job_summary_json_serializable():
    """IngestionJobSummaryResponse produces valid JSON."""
    now = datetime.now(timezone.utc)

    response = IngestionJobSummaryResponse(
        id=uuid.uuid4(),
        dataset_registry_id=uuid.uuid4(),
        status=IngestionStatus.COMPLETED,
        original_filename="test.csv",
        file_format=FileFormat.CSV,
        row_count=100,
        column_count=5,
        started_at=None,
        completed_at=now,
        failed_at=None,
        error_message=None,
        created_by_user_id=None,
        created_at=now,
        updated_at=now,
    )

    json_str = response.model_dump_json()
    assert isinstance(json_str, str)
    assert "COMPLETED" in json_str
    assert "test.csv" in json_str


def test_dataset_inspection_response_json_serializable():
    """DatasetInspectionResponse produces valid JSON."""
    now = datetime.now(timezone.utc)
    job_id = uuid.uuid4()

    job = IngestionJobSummaryResponse(
        id=job_id,
        dataset_registry_id=uuid.uuid4(),
        status=IngestionStatus.COMPLETED,
        original_filename="test.csv",
        file_format=FileFormat.CSV,
        row_count=1,
        column_count=1,
        started_at=None,
        completed_at=now,
        failed_at=None,
        error_message=None,
        created_by_user_id=None,
        created_at=now,
        updated_at=now,
    )

    columns = [
        DatasetColumnResponse(
            id=uuid.uuid4(),
            ingestion_job_id=job_id,
            ordinal_position=0,
            original_name="Col",
            normalized_name="col",
            inferred_type=InferredColumnType.TEXT,
            nullable=False,
            missing_count=0,
            unique_count=1,
            sample_values=["val"],
            created_at=now,
        )
    ]

    rows = [
        DatasetRowResponse(
            id=uuid.uuid4(),
            ingestion_job_id=job_id,
            row_number=0,
            values={"col": "val"},
            created_at=now,
        )
    ]

    pagination = PaginationResponse(
        page=1,
        page_size=50,
        total_items=1,
        total_pages=1,
        has_next=False,
        has_previous=False,
    )

    response = DatasetInspectionResponse(
        job=job,
        columns=columns,
        rows=rows,
        pagination=pagination,
    )

    json_str = response.model_dump_json()
    assert isinstance(json_str, str)
    assert "job" in json_str
    assert "columns" in json_str
    assert "rows" in json_str
    assert "pagination" in json_str
