from __future__ import annotations

import logging
from dataclasses import dataclass
from time import perf_counter

from app.domain.analytics.compatibility import (
    is_dimension_eligible,
    supported_aggregations,
)
from app.domain.analytics.contracts import (
    AnalyticsDimensionDescriptor,
    AnalyticsMeasureDescriptor,
    DatasetColumnDescriptor,
    DatasetDetails,
    DatasetListResult,
    DatasetPreviewResult,
    DatasetStatistics,
    DatasetSummary,
)
from app.domain.analytics.exceptions import (
    DatasetNotAnalyticsReadyError,
    IncompleteIngestionJobError,
    UnknownIngestionJobError,
)
from app.models.data_source import DatasetRegistry, DataSource
from app.models.ingestion import (
    DatasetColumn,
    DatasetRow,
    InferredColumnType,
    IngestionJob,
    IngestionStatus,
)
from app.repositories.dataset_column_repository import DatasetColumnRepository
from app.repositories.dataset_row_repository import DatasetRowRepository
from sqlalchemy import desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class DatasetDiscoveryRow:
    job: IngestionJob
    dataset_registry: DatasetRegistry
    data_source: DataSource


class DatasetDiscoveryRepository:
    """Read-only analytics dataset discovery repository."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._column_repo = DatasetColumnRepository(session)
        self._row_repo = DatasetRowRepository(session)

    async def count_analytics_ready_datasets(self) -> int:
        result = await self._session.execute(
            select(func.count())
            .select_from(IngestionJob)
            .where(
                IngestionJob.status == IngestionStatus.COMPLETED,
                IngestionJob.column_count.isnot(None),
                IngestionJob.column_count > 0,
            )
        )
        return result.scalar_one()

    async def list_analytics_ready_datasets(
        self, *, offset: int = 0, limit: int = 50
    ) -> list[DatasetDiscoveryRow]:
        result = await self._session.execute(
            select(IngestionJob, DatasetRegistry, DataSource)
            .join(DatasetRegistry, IngestionJob.dataset_registry)
            .join(DataSource, DatasetRegistry.data_source)
            .where(
                IngestionJob.status == IngestionStatus.COMPLETED,
                IngestionJob.column_count.isnot(None),
                IngestionJob.column_count > 0,
            )
            .order_by(desc(IngestionJob.completed_at), desc(IngestionJob.id))
            .offset(max(offset, 0))
            .limit(max(limit, 0))
        )
        return [
            DatasetDiscoveryRow(job=job, dataset_registry=registry, data_source=source)
            for job, registry, source in result.all()
        ]

    async def get_job_with_registry_and_source(
        self, ingestion_job_id
    ) -> DatasetDiscoveryRow | None:
        result = await self._session.execute(
            select(IngestionJob, DatasetRegistry, DataSource)
            .join(DatasetRegistry, IngestionJob.dataset_registry)
            .join(DataSource, DatasetRegistry.data_source)
            .where(IngestionJob.id == ingestion_job_id)
        )
        row = result.one_or_none()
        if row is None:
            return None
        job, registry, source = row
        return DatasetDiscoveryRow(job=job, dataset_registry=registry, data_source=source)

    async def list_columns(self, ingestion_job_id) -> list[DatasetColumn]:
        return await self._column_repo.list_by_ingestion_job(ingestion_job_id)

    async def preview_rows(self, ingestion_job_id, limit: int) -> list[DatasetRow]:
        return await self._row_repo.list_by_ingestion_job(ingestion_job_id, offset=0, limit=limit)


class DatasetDiscoveryService:
    """Service layer for analytics dataset discovery."""

    def __init__(self, repository: DatasetDiscoveryRepository) -> None:
        self._repository = repository

    async def list_datasets(self, *, limit: int = 50, offset: int = 0) -> DatasetListResult:
        start = perf_counter()
        total = await self._repository.count_analytics_ready_datasets()
        rows = await self._repository.list_analytics_ready_datasets(offset=offset, limit=limit)
        items = [self._map_dataset_summary(entry) for entry in rows]
        has_more = offset + len(items) < total
        duration_ms = round((perf_counter() - start) * 1000, 2)
        logger.info(
            "Analytics dataset list retrieved",
            extra={
                "operation": "list_datasets",
                "limit": limit,
                "offset": offset,
                "returned_count": len(items),
                "total": total,
                "duration_ms": duration_ms,
            },
        )
        return DatasetListResult(
            items=items,
            total=total,
            limit=limit,
            offset=offset,
            has_more=has_more,
        )

    async def get_dataset_details(self, ingestion_job_id) -> DatasetDetails:
        start = perf_counter()
        row = await self._repository.get_job_with_registry_and_source(ingestion_job_id)
        if row is None:
            raise UnknownIngestionJobError("unknown ingestion_job_id")
        if row.job.status != IngestionStatus.COMPLETED:
            raise IncompleteIngestionJobError("ingestion job is not complete")
        if row.job.column_count is None or row.job.column_count == 0:
            raise DatasetNotAnalyticsReadyError("dataset is not analytics-ready")

        columns = await self._repository.list_columns(ingestion_job_id)
        details = DatasetDetails(
            summary=self._map_dataset_summary(row),
            columns=[self._map_column_descriptor(column) for column in columns],
            available_dimensions=[
                self._map_dimension_descriptor(column)
                for column in columns
                if is_dimension_eligible(column.inferred_type)
            ],
            available_measures=[
                self._map_measure_descriptor(column)
                for column in columns
                if supported_aggregations(column.inferred_type)
            ],
            preview_available=True,
            analytics_ready=True,
        )
        duration_ms = round((perf_counter() - start) * 1000, 2)
        logger.info(
            "Analytics dataset details retrieved",
            extra={
                "operation": "get_dataset_details",
                "ingestion_job_id": str(ingestion_job_id),
                "column_count": len(columns),
                "dimension_count": len(details.available_dimensions),
                "measure_count": len(details.available_measures),
                "duration_ms": duration_ms,
            },
        )
        return details

    async def get_schema(self, ingestion_job_id) -> list[DatasetColumnDescriptor]:
        row = await self._repository.get_job_with_registry_and_source(ingestion_job_id)
        if row is None:
            raise UnknownIngestionJobError("unknown ingestion_job_id")
        if row.job.status != IngestionStatus.COMPLETED:
            raise IncompleteIngestionJobError("ingestion job is not complete")
        if row.job.column_count is None or row.job.column_count == 0:
            raise DatasetNotAnalyticsReadyError("dataset is not analytics-ready")

        columns = await self._repository.list_columns(ingestion_job_id)
        descriptors = [self._map_column_descriptor(column) for column in columns]
        return descriptors

    async def get_dimensions(self, ingestion_job_id) -> list[AnalyticsDimensionDescriptor]:
        row = await self._repository.get_job_with_registry_and_source(ingestion_job_id)
        if row is None:
            raise UnknownIngestionJobError("unknown ingestion_job_id")
        if row.job.status != IngestionStatus.COMPLETED:
            raise IncompleteIngestionJobError("ingestion job is not complete")
        if row.job.column_count is None or row.job.column_count == 0:
            raise DatasetNotAnalyticsReadyError("dataset is not analytics-ready")

        columns = await self._repository.list_columns(ingestion_job_id)
        return [
            self._map_dimension_descriptor(column)
            for column in columns
            if is_dimension_eligible(column.inferred_type)
        ]

    async def get_measures(self, ingestion_job_id) -> list[AnalyticsMeasureDescriptor]:
        row = await self._repository.get_job_with_registry_and_source(ingestion_job_id)
        if row is None:
            raise UnknownIngestionJobError("unknown ingestion_job_id")
        if row.job.status != IngestionStatus.COMPLETED:
            raise IncompleteIngestionJobError("ingestion job is not complete")
        if row.job.column_count is None or row.job.column_count == 0:
            raise DatasetNotAnalyticsReadyError("dataset is not analytics-ready")

        columns = await self._repository.list_columns(ingestion_job_id)
        return [
            self._map_measure_descriptor(column)
            for column in columns
            if supported_aggregations(column.inferred_type)
        ]

    async def get_preview(self, ingestion_job_id, limit: int = 10) -> DatasetPreviewResult:
        row = await self._repository.get_job_with_registry_and_source(ingestion_job_id)
        if row is None:
            raise UnknownIngestionJobError("unknown ingestion_job_id")
        if row.job.status != IngestionStatus.COMPLETED:
            raise IncompleteIngestionJobError("ingestion job is not complete")
        if row.job.column_count is None or row.job.column_count == 0:
            raise DatasetNotAnalyticsReadyError("dataset is not analytics-ready")

        columns = await self._repository.list_columns(ingestion_job_id)
        rows = await self._repository.preview_rows(ingestion_job_id, limit)
        preview = DatasetPreviewResult(
            ingestion_job_id=ingestion_job_id,
            columns=[column.normalized_name for column in columns],
            rows=[row.values for row in rows],
            limit=limit,
            returned_count=len(rows),
        )
        return preview

    async def get_statistics(self, ingestion_job_id) -> DatasetStatistics:
        row = await self._repository.get_job_with_registry_and_source(ingestion_job_id)
        if row is None:
            raise UnknownIngestionJobError("unknown ingestion_job_id")
        if row.job.status != IngestionStatus.COMPLETED:
            raise IncompleteIngestionJobError("ingestion job is not complete")
        if row.job.column_count is None or row.job.column_count == 0:
            raise DatasetNotAnalyticsReadyError("dataset is not analytics-ready")

        columns = await self._repository.list_columns(ingestion_job_id)
        stats = DatasetStatistics(
            ingestion_job_id=ingestion_job_id,
            row_count=row.job.row_count or 0,
            column_count=len(columns),
            nullable_column_count=sum(1 for column in columns if column.nullable),
            numeric_column_count=sum(
                1
                for column in columns
                if column.inferred_type in {InferredColumnType.INTEGER, InferredColumnType.DECIMAL}
            ),
            text_column_count=sum(
                1 for column in columns if column.inferred_type == InferredColumnType.TEXT
            ),
            date_column_count=sum(
                1 for column in columns if column.inferred_type == InferredColumnType.DATE
            ),
            datetime_column_count=sum(
                1 for column in columns if column.inferred_type == InferredColumnType.DATETIME
            ),
            boolean_column_count=sum(
                1 for column in columns if column.inferred_type == InferredColumnType.BOOLEAN
            ),
            completed_at=row.job.completed_at,
        )
        return stats

    def _map_dataset_summary(self, entry: DatasetDiscoveryRow) -> DatasetSummary:
        return DatasetSummary(
            ingestion_job_id=entry.job.id,
            source_name=entry.data_source.name,
            dataset_name=entry.dataset_registry.dataset_name,
            status=entry.job.status,
            row_count=entry.job.row_count or 0,
            column_count=entry.job.column_count or 0,
            completed_at=entry.job.completed_at,
            created_at=entry.job.created_at,
            description=entry.dataset_registry.description,
        )

    def _map_column_descriptor(self, column: DatasetColumn) -> DatasetColumnDescriptor:
        return DatasetColumnDescriptor(
            identifier=column.normalized_name,
            display_name=column.original_name,
            inferred_type=column.inferred_type,
            nullable=column.nullable,
            ordinal_position=column.ordinal_position,
            semantic_role=None,
            dimension_eligible=is_dimension_eligible(column.inferred_type),
            measure_eligible=bool(supported_aggregations(column.inferred_type)),
            supported_aggregations=list(supported_aggregations(column.inferred_type)),
        )

    def _map_dimension_descriptor(self, column: DatasetColumn) -> AnalyticsDimensionDescriptor:
        return AnalyticsDimensionDescriptor(
            identifier=column.normalized_name,
            display_name=column.original_name,
            data_type=column.inferred_type,
        )

    def _map_measure_descriptor(self, column: DatasetColumn) -> AnalyticsMeasureDescriptor:
        return AnalyticsMeasureDescriptor(
            identifier=column.normalized_name,
            display_name=column.original_name,
            data_type=column.inferred_type,
            supported_aggregations=list(supported_aggregations(column.inferred_type)),
        )
