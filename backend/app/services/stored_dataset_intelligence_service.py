"""Application boundary for deterministic intelligence over persisted datasets."""

from __future__ import annotations

from app.domain.analytics.contracts import (
    AggregationFunction,
    AnalyticsQuery,
    DatasetReference,
    Dimension,
    Measure,
)
from app.domain.analytics.discovery import DatasetDiscoveryService
from app.domain.analytics.service import AnalyticsService
from app.models.ingestion import InferredColumnType
from app.schemas.intelligence import (
    ConfidenceStatus,
    DatasetIntelligenceResponse,
    InsightResult,
    InsightType,
    IntelligenceDatasetSummary,
    KpiResult,
    KpiType,
    VisualizationArtifact,
    VisualizationType,
)
from app.services.data_intelligence_service import DataIntelligenceService


class StoredDatasetIntelligenceService:
    """Loads bounded source data and delegates computation to Phase 9.1 engines."""

    SAMPLE_LIMIT = 5_000
    ARTIFACT_LIMIT = 1_000

    def __init__(
        self,
        discovery: DatasetDiscoveryService,
        analytics: AnalyticsService,
        intelligence: DataIntelligenceService | None = None,
    ) -> None:
        self._discovery = discovery
        self._analytics = analytics
        self._intelligence = intelligence or DataIntelligenceService()

    async def analyze(self, ingestion_job_id) -> DatasetIntelligenceResponse:
        details = await self._discovery.get_dataset_details(ingestion_job_id)
        summary = details.summary
        columns = await self._discovery._repository.list_columns(ingestion_job_id)
        rows = await self._discovery._repository.preview_rows(ingestion_job_id, self.SAMPLE_LIMIT)

        column_inputs = [
            {
                "identifier": column.normalized_name,
                "display_name": column.original_name,
                "inferred_type": column.inferred_type.value,
                "data_type": column.inferred_type.value,
                "role": self._role(column.inferred_type),
                "cardinality": column.unique_count,
                "null_count": column.missing_count,
                "total_count": summary.row_count,
                "sample_values": column.sample_values or [],
            }
            for column in columns
        ]
        row_values = [row.values for row in rows]
        result = self._intelligence.analyze_dataset(
            str(ingestion_job_id), column_inputs, row_values, summary.row_count
        )

        exact_kpis, exact_insights = await self._build_exact_metrics(
            ingestion_job_id, columns, summary.row_count
        )

        visualizations: list[VisualizationArtifact] = []
        warnings = list(result.warnings)
        for recommendation in result.visualization_recommendations:
            artifact = await self._build_artifact(
                ingestion_job_id, recommendation, summary.row_count
            )
            if artifact is None:
                warnings.append(
                    f"Visualization '{recommendation.visualization_type.value}' was skipped because its result shape was unsupported."
                )
            else:
                visualizations.append(artifact)

        return DatasetIntelligenceResponse(
            dataset=IntelligenceDatasetSummary(
                id=summary.ingestion_job_id,
                name=summary.dataset_name,
                row_count=summary.row_count,
                column_count=summary.column_count,
                imported_at=summary.completed_at or summary.created_at,
            ),
            profile={"columns": result.columns, "row_count": summary.row_count},
            kpis=exact_kpis,
            visualizations=visualizations,
            insights=exact_insights,
            quality_notes=result.data_quality_notes,
            provenance={
                **result.provenance,
                "source": "stored_dataset",
                "sample_limit": self.SAMPLE_LIMIT,
                "analytics_service": "AnalyticsService",
                "aggregation_authority": "AnalyticsRepository",
            },
            warnings=warnings,
            analysis_scope="FULL_DATASET",
            sample_size=len(rows),
            total_rows=summary.row_count,
            coverage_ratio=(len(rows) / summary.row_count) if summary.row_count else 0.0,
        )

    async def _build_exact_metrics(self, ingestion_job_id, columns, total_rows):
        """Calculate dataset-level numeric facts through the analytics planner/repository."""
        numeric = [
            column
            for column in columns
            if column.inferred_type in {InferredColumnType.INTEGER, InferredColumnType.DECIMAL}
        ]
        kpis: list[KpiResult] = []
        insights: list[InsightResult] = []
        for column in numeric:
            aliases = {
                "total": AggregationFunction.SUM,
                "count": AggregationFunction.COUNT,
                "average": AggregationFunction.AVERAGE,
                "minimum": AggregationFunction.MINIMUM,
                "maximum": AggregationFunction.MAXIMUM,
            }
            query = AnalyticsQuery(
                dataset_reference=DatasetReference(ingestion_job_id=ingestion_job_id),
                measures=[
                    Measure(
                        aggregation=aggregation, column_name=column.normalized_name, alias=alias
                    )
                    for alias, aggregation in aliases.items()
                ],
                limit=1,
            )
            values = (await self._analytics.execute(query)).rows[0] if total_rows else {}
            for alias, aggregation in aliases.items():
                value = self._json_number(values.get(alias))
                if value is None:
                    continue
                kpi_type = {
                    "total": KpiType.TOTAL,
                    "count": KpiType.COUNT,
                    "average": KpiType.AVERAGE,
                    "minimum": KpiType.MINIMUM,
                    "maximum": KpiType.MAXIMUM,
                }[alias]
                kpis.append(
                    KpiResult(
                        label=f"{aggregation.value.title()} {column.original_name}",
                        metric=column.normalized_name,
                        kpi_type=kpi_type,
                        aggregation=aggregation.value,
                        value=value,
                        scope="all_rows",
                        source_reference=str(ingestion_job_id),
                        confidence=ConfidenceStatus.SUPPORTED,
                        analysis_scope="FULL_DATASET",
                        sample_size=0,
                        total_rows=total_rows,
                        coverage_ratio=1.0,
                    )
                )
            distinct_query = AnalyticsQuery(
                dataset_reference=DatasetReference(ingestion_job_id=ingestion_job_id),
                measures=[
                    Measure(
                        aggregation=AggregationFunction.COUNT_DISTINCT,
                        column_name=column.normalized_name,
                        alias="distinct",
                    )
                ],
                limit=1,
            )
            distinct_value = (
                self._json_number(
                    (await self._analytics.execute(distinct_query)).rows[0].get("distinct")
                )
                if total_rows
                else None
            )
            if distinct_value is not None:
                kpis.append(
                    KpiResult(
                        label=f"Distinct values in {column.original_name}",
                        metric=column.normalized_name,
                        kpi_type=KpiType.COUNT_DISTINCT,
                        aggregation=AggregationFunction.COUNT_DISTINCT.value,
                        value=distinct_value,
                        scope="all_rows",
                        source_reference=str(ingestion_job_id),
                        confidence=ConfidenceStatus.SUPPORTED,
                        analysis_scope="FULL_DATASET",
                        sample_size=0,
                        total_rows=total_rows,
                        coverage_ratio=1.0,
                    )
                )
            for insight_type, alias, operation in (
                (InsightType.HIGHEST_CATEGORY, "maximum", "max"),
                (InsightType.LOWEST_CATEGORY, "minimum", "min"),
            ):
                value = self._json_number(values.get(alias))
                if value is not None:
                    insights.append(
                        InsightResult(
                            insight_type=insight_type,
                            metric=column.normalized_name,
                            subject=f"{operation.title()} value in {column.original_name}",
                            value=value,
                            statement_data={
                                "operation": operation,
                                "column": column.normalized_name,
                                "result": value,
                            },
                            source_reference=str(ingestion_job_id),
                            analysis_scope="FULL_DATASET",
                            sample_size=0,
                            total_rows=total_rows,
                            coverage_ratio=1.0,
                        )
                    )

        dimensions = [
            column
            for column in columns
            if column.inferred_type
            in {
                InferredColumnType.TEXT,
                InferredColumnType.DATE,
                InferredColumnType.DATETIME,
            }
        ]
        for dimension in dimensions:
            distinct_query = AnalyticsQuery(
                dataset_reference=DatasetReference(ingestion_job_id=ingestion_job_id),
                measures=[
                    Measure(
                        aggregation=AggregationFunction.COUNT_DISTINCT,
                        column_name=dimension.normalized_name,
                        alias="distinct",
                    )
                ],
                limit=1,
            )
            distinct_value = (
                self._json_number(
                    (await self._analytics.execute(distinct_query)).rows[0].get("distinct")
                )
                if total_rows
                else None
            )
            if distinct_value is not None:
                kpis.append(
                    KpiResult(
                        label=f"Distinct values in {dimension.original_name}",
                        metric=dimension.normalized_name,
                        kpi_type=KpiType.COUNT_DISTINCT,
                        aggregation=AggregationFunction.COUNT_DISTINCT.value,
                        value=distinct_value,
                        scope="all_rows",
                        source_reference=str(ingestion_job_id),
                        confidence=ConfidenceStatus.SUPPORTED,
                        analysis_scope="FULL_DATASET",
                        sample_size=0,
                        total_rows=total_rows,
                        coverage_ratio=1.0,
                    )
                )
        for dimension in dimensions[:10]:
            for measure_column in numeric[:5]:
                query = AnalyticsQuery(
                    dataset_reference=DatasetReference(ingestion_job_id=ingestion_job_id),
                    dimensions=[Dimension(column_name=dimension.normalized_name)],
                    measures=[
                        Measure(
                            aggregation=AggregationFunction.SUM,
                            column_name=measure_column.normalized_name,
                            alias="value",
                        )
                    ],
                    limit=self.ARTIFACT_LIMIT,
                )
                grouped = (await self._analytics.execute(query)).rows
                grouped = [
                    row
                    for row in grouped
                    if row.get(dimension.normalized_name) is not None
                    and row.get("value") is not None
                ]
                if not grouped:
                    continue
                highest = max(grouped, key=lambda row: float(row["value"]))
                lowest = min(grouped, key=lambda row: float(row["value"]))
                for insight_type, selected, operation in (
                    (
                        InsightType.HIGHEST_PERIOD
                        if dimension.inferred_type
                        in {InferredColumnType.DATE, InferredColumnType.DATETIME}
                        else InsightType.HIGHEST_CATEGORY,
                        highest,
                        "max",
                    ),
                    (
                        InsightType.LOWEST_PERIOD
                        if dimension.inferred_type
                        in {InferredColumnType.DATE, InferredColumnType.DATETIME}
                        else InsightType.LOWEST_CATEGORY,
                        lowest,
                        "min",
                    ),
                ):
                    value = self._json_number(selected["value"])
                    subject = str(selected[dimension.normalized_name])
                    kpis.append(
                        KpiResult(
                            label=f"{operation.title()} {measure_column.original_name} by {dimension.original_name}",
                            metric=measure_column.normalized_name,
                            kpi_type=(
                                KpiType.HIGHEST_PERIOD
                                if insight_type == InsightType.HIGHEST_PERIOD
                                else KpiType.LOWEST_PERIOD
                                if insight_type == InsightType.LOWEST_PERIOD
                                else KpiType.HIGHEST_CATEGORY
                                if insight_type == InsightType.HIGHEST_CATEGORY
                                else KpiType.LOWEST_CATEGORY
                            ),
                            aggregation=AggregationFunction.SUM.value,
                            value=value,
                            dimension=dimension.normalized_name,
                            dimension_value=subject,
                            period=subject
                            if insight_type
                            in {InsightType.HIGHEST_PERIOD, InsightType.LOWEST_PERIOD}
                            else None,
                            scope="all_rows",
                            source_reference=str(ingestion_job_id),
                            analysis_scope="FULL_DATASET",
                            sample_size=0,
                            total_rows=total_rows,
                            coverage_ratio=1.0,
                        )
                    )
                    insights.append(
                        InsightResult(
                            insight_type=insight_type,
                            metric=measure_column.normalized_name,
                            dimension=dimension.normalized_name,
                            subject=subject,
                            value=value,
                            statement_data={
                                "operation": operation,
                                "dimension": dimension.normalized_name,
                                "measure": measure_column.normalized_name,
                                "subject": subject,
                                "result": value,
                            },
                            period=subject
                            if insight_type
                            in {InsightType.HIGHEST_PERIOD, InsightType.LOWEST_PERIOD}
                            else None,
                            source_reference=str(ingestion_job_id),
                            analysis_scope="FULL_DATASET",
                            sample_size=0,
                            total_rows=total_rows,
                            coverage_ratio=1.0,
                        )
                    )
        return kpis, insights

    @staticmethod
    def _json_number(value):
        if value is None:
            return None
        try:
            number = float(value)
            return int(number) if number.is_integer() else number
        except (TypeError, ValueError):
            return None

    async def _build_artifact(
        self, ingestion_job_id, recommendation, total_rows: int
    ) -> VisualizationArtifact | None:
        chart_type = recommendation.visualization_type
        if chart_type == VisualizationType.TABLE:
            rows = await self._discovery._repository.preview_rows(ingestion_job_id, 100)
            data = [row.values for row in rows]
        elif recommendation.dimension and recommendation.measure:
            aggregation = self._aggregation(recommendation.aggregation)
            if aggregation is None:
                return None
            query = AnalyticsQuery(
                dataset_reference=DatasetReference(ingestion_job_id=ingestion_job_id),
                dimensions=[Dimension(column_name=recommendation.dimension)],
                measures=[
                    Measure(
                        aggregation=aggregation, column_name=recommendation.measure, alias="value"
                    )
                ],
                limit=self.ARTIFACT_LIMIT,
            )
            data = (await self._analytics.execute(query)).rows
        else:
            return None

        dimension = (
            {"column": recommendation.dimension, "label": recommendation.dimension}
            if recommendation.dimension
            else None
        )
        measure = (
            {
                "column": recommendation.measure,
                "aggregation": recommendation.aggregation or "SUM",
                "unit": "",
            }
            if recommendation.measure
            else None
        )
        label = recommendation.dimension or recommendation.measure or "dataset"
        title = recommendation.title or self._title(chart_type, label, recommendation.measure)
        return VisualizationArtifact(
            id=recommendation.id,
            type=chart_type,
            title=title,
            reason_code=recommendation.reason_code,
            dimension=dimension,
            measure=measure,
            series=recommendation.series,
            data=data,
            warnings=recommendation.warnings,
            provenance={"dataset_id": str(ingestion_job_id), "filters": recommendation.filters},
            analysis_scope="PREVIEW" if chart_type == VisualizationType.TABLE else "FULL_DATASET",
            sample_size=100 if chart_type == VisualizationType.TABLE else None,
            total_rows=total_rows,
            coverage_ratio=(100 / total_rows)
            if chart_type == VisualizationType.TABLE and total_rows
            else (1.0 if chart_type != VisualizationType.TABLE else 0.0),
        )

    @staticmethod
    def _role(column_type: InferredColumnType) -> str:
        return (
            "measure"
            if column_type in {InferredColumnType.INTEGER, InferredColumnType.DECIMAL}
            else "dimension"
        )

    @staticmethod
    def _aggregation(value: str | None) -> AggregationFunction | None:
        values = {item.value: item for item in AggregationFunction}
        return values.get(value or "SUM")

    @staticmethod
    def _title(chart_type: VisualizationType, label: str, measure: str | None) -> str:
        if chart_type == VisualizationType.LINE:
            return f"{measure or label} over time"
        if chart_type == VisualizationType.BAR:
            return f"{measure or label} by {label}"
        if chart_type == VisualizationType.PIE:
            return f"{measure or label} by {label}"
        return f"{label} table"
