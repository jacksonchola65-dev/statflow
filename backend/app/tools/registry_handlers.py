"""Governed handlers registered by the internal StatFlow tool registry."""

from __future__ import annotations

from typing import cast

from app.domain.analytics.contracts import (
    AnalyticsQuery,
    DatasetReference,
    Dimension,
    FilterClause,
    Measure,
)
from app.domain.analytics.exceptions import (
    DatasetNotAnalyticsReadyError,
    IncompleteIngestionJobError,
    InvalidAggregationError,
    InvalidIdentifierError,
    UnknownIngestionJobError,
)
from app.domain.analytics.service import AnalyticsService
from app.domain.decision import BusinessLocationMode
from app.services.decision_api_service import DecisionApiService
from app.services.stored_dataset_intelligence_service import StoredDatasetIntelligenceService
from pydantic import BaseModel

from .contracts import (
    DatasetToolArguments,
    ExplainProvenanceArguments,
    IdentifyEvidenceGapsArguments,
    RunDatasetAnalysisArguments,
    RunDecisionArguments,
    ToolAuthority,
    ToolExecutionContext,
    ToolStatus,
)
from .registry import (
    ToolDefinition,
    ToolExecutionError,
    ToolHandler,
    ToolHandlerResult,
    ToolRegistry,
)


class StatFlowToolHandlers:
    """Adapt typed tool intents to existing governed application services."""

    MAX_ANALYSIS_ROWS = 100

    def __init__(self, discovery, intelligence: StoredDatasetIntelligenceService, analytics: AnalyticsService, db):
        self.discovery = discovery
        self.intelligence = intelligence
        self.analytics = analytics
        self.db = db

    async def get_dataset_metadata(self, _context: ToolExecutionContext, args: DatasetToolArguments) -> ToolHandlerResult:
        try:
            details = await self.discovery.get_dataset_details(args.dataset_id)
        except (UnknownIngestionJobError, IncompleteIngestionJobError, DatasetNotAnalyticsReadyError) as exc:
            raise ToolExecutionError(ToolStatus.NOT_FOUND, "DATASET_NOT_FOUND") from exc
        return ToolHandlerResult(
            data=details.model_dump(mode="json"),
            authority=ToolAuthority.DETERMINISTIC,
            provenance={"dataset_id": str(args.dataset_id), "source": "DatasetDiscoveryService"},
        )

    async def analyze_dataset(self, _context: ToolExecutionContext, args: DatasetToolArguments) -> ToolHandlerResult:
        try:
            result = await self.intelligence.analyze(args.dataset_id)
        except (UnknownIngestionJobError, IncompleteIngestionJobError, DatasetNotAnalyticsReadyError) as exc:
            raise ToolExecutionError(ToolStatus.NOT_FOUND, "DATASET_NOT_FOUND") from exc
        return ToolHandlerResult(
            data=result.model_dump(mode="json"),
            authority=ToolAuthority.DETERMINISTIC,
            warnings=tuple(result.warnings),
            provenance={**result.provenance, "dataset_id": str(args.dataset_id)},
        )

    async def run_dataset_analysis(self, _context: ToolExecutionContext, args: RunDatasetAnalysisArguments) -> ToolHandlerResult:
        if args.limit > self.MAX_ANALYSIS_ROWS:
            raise ToolExecutionError(ToolStatus.RESULT_LIMIT_EXCEEDED, "RESULT_LIMIT_EXCEEDED")
        if args.aggregation.value != "COUNT" and args.measure is None:
            raise ToolExecutionError(ToolStatus.INVALID_ARGUMENTS, "MEASURE_REQUIRED")
        query = AnalyticsQuery(
            dataset_reference=DatasetReference(ingestion_job_id=args.dataset_id),
            dimensions=[Dimension(column_name=args.dimension)] if args.dimension else [],
            measures=[Measure(aggregation=args.aggregation, column_name=args.measure, alias="value")],
            filters=[FilterClause(column_name=item.column, operator=item.operator, value=item.value) for item in args.filters],
            limit=args.limit,
            offset=args.offset,
        )
        try:
            result = await self.analytics.execute(query)
        except (UnknownIngestionJobError, IncompleteIngestionJobError) as exc:
            raise ToolExecutionError(ToolStatus.NOT_FOUND, "DATASET_NOT_FOUND") from exc
        except (InvalidIdentifierError, InvalidAggregationError, ValueError) as exc:
            raise ToolExecutionError(ToolStatus.INVALID_ARGUMENTS, "INVALID_ANALYTICS_ARGUMENTS") from exc
        return ToolHandlerResult(
            data=result.model_dump(mode="json"),
            authority=ToolAuthority.DETERMINISTIC,
            provenance={
                "dataset_id": str(args.dataset_id),
                "dimension": args.dimension,
                "measure": args.measure,
                "aggregation": args.aggregation.value,
                "filters": [item.model_dump(mode="json") for item in args.filters],
            },
        )

    async def explain_provenance(self, _context: ToolExecutionContext, args: ExplainProvenanceArguments) -> ToolHandlerResult:
        if args.dimension is None and args.measure is None:
            raise ToolExecutionError(ToolStatus.INVALID_ARGUMENTS, "PROVENANCE_TARGET_REQUIRED")
        try:
            details = await self.discovery.get_dataset_details(args.dataset_id)
        except (UnknownIngestionJobError, IncompleteIngestionJobError, DatasetNotAnalyticsReadyError) as exc:
            raise ToolExecutionError(ToolStatus.NOT_FOUND, "DATASET_NOT_FOUND") from exc
        dimension_names = {item.identifier for item in details.available_dimensions}
        measure_map = {item.identifier: item for item in details.available_measures}
        if args.dimension is not None and args.dimension not in dimension_names:
            raise ToolExecutionError(ToolStatus.INVALID_ARGUMENTS, "UNKNOWN_DIMENSION")
        if args.measure is not None:
            measure = measure_map.get(args.measure)
            if measure is None:
                raise ToolExecutionError(ToolStatus.INVALID_ARGUMENTS, "UNKNOWN_MEASURE")
            if args.aggregation is not None and args.aggregation not in measure.supported_aggregations:
                raise ToolExecutionError(ToolStatus.INVALID_ARGUMENTS, "UNSUPPORTED_AGGREGATION")
        return ToolHandlerResult(
            data={
                "dataset_id": str(args.dataset_id),
                "dimension": args.dimension,
                "measure": args.measure,
                "aggregation": args.aggregation.value if args.aggregation else None,
                "scope": args.scope,
                "filters": [],
            },
            authority=ToolAuthority.PREVIEW if args.scope == "PREVIEW" else ToolAuthority.DETERMINISTIC,
            provenance={"source": "canonical_tool_arguments", "dataset_id": str(args.dataset_id)},
        )

    async def run_decision(self, _context: ToolExecutionContext, args: RunDecisionArguments) -> ToolHandlerResult:
        mode = (
            BusinessLocationMode.DECISION_READY
            if args.mode == "PRODUCTION"
            else BusinessLocationMode.EXPLORATORY
        )
        try:
            result = await DecisionApiService(self.db).evaluate(
                model_id=args.model_id,
                province_code=args.province_code,
                mode=mode,
                business_category=args.business_category,
                reference_year=args.reference_year,
                criterion_weights=args.criterion_weights,
            )
        except Exception as exc:
            from fastapi import HTTPException

            if isinstance(exc, HTTPException):
                if exc.status_code == 404:
                    raise ToolExecutionError(ToolStatus.NOT_FOUND, "DECISION_MODEL_NOT_FOUND") from exc
                raise ToolExecutionError(ToolStatus.INVALID_ARGUMENTS, "DECISION_REQUEST_REJECTED") from exc
            raise
        readiness = str(result.get("decision_readiness", "")).lower()
        status = ToolStatus.INSUFFICIENT_EVIDENCE if "insufficient" in readiness else ToolStatus.SUCCESS
        authority = ToolAuthority.EXPLORATORY if mode is BusinessLocationMode.EXPLORATORY else ToolAuthority.DECISION_GOVERNED
        return ToolHandlerResult(
            data=result,
            authority=authority,
            status=status,
            error_code="INSUFFICIENT_EVIDENCE" if status is ToolStatus.INSUFFICIENT_EVIDENCE else None,
            provenance={"model_id": args.model_id, "mode": args.mode},
        )

    async def identify_evidence_gaps(self, context: ToolExecutionContext, args: IdentifyEvidenceGapsArguments) -> ToolHandlerResult:
        result = await self.run_decision(context, args)
        return ToolHandlerResult(
            data={
                "decision_readiness": result.data.get("decision_readiness"),
                "blockers": result.data.get("blockers", ()),
                "blocker_reasons": result.data.get("blocker_reasons", ()),
                "criterion_readiness": result.data.get("criterion_readiness", ()),
                "evidence_backlog": result.data.get("evidence_backlog", ()),
            },
            authority=ToolAuthority.EVIDENCE_GOVERNED,
            status=result.status,
            error_code=result.error_code,
            provenance=result.provenance,
        )


def register_statflow_tools(registry: ToolRegistry, handlers: StatFlowToolHandlers) -> ToolRegistry:
    definitions = [
        ("get_dataset_metadata", "Return governed metadata for one stored analytics dataset.", DatasetToolArguments, handlers.get_dataset_metadata, None),
        ("analyze_dataset", "Run deterministic intelligence over one stored dataset.", DatasetToolArguments, handlers.analyze_dataset, 1000),
        ("run_dataset_analysis", "Run a bounded typed aggregation against a stored dataset.", RunDatasetAnalysisArguments, handlers.run_dataset_analysis, 100),
        ("explain_provenance", "Return structured calculation provenance for a dataset analysis target.", ExplainProvenanceArguments, handlers.explain_provenance, None),
        ("run_decision", "Run the governed Business Location Decision Intelligence application service.", RunDecisionArguments, handlers.run_decision, None),
        ("identify_evidence_gaps", "Return deterministic decision evidence blockers and readiness facts.", IdentifyEvidenceGapsArguments, handlers.identify_evidence_gaps, None),
    ]
    for name, description, model, handler, max_rows in definitions:
        registry.register(ToolDefinition(
            name=name,
            version=1,
            description=description,
            arguments_model=cast(type[BaseModel], model),
            handler=cast(ToolHandler, handler),
            max_result_rows=max_rows,
        ))
    return registry
