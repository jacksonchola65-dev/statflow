from __future__ import annotations


class AnalyticsQueryError(Exception):
    """Base class for analytics-domain errors."""


class InvalidIdentifierError(AnalyticsQueryError, ValueError):
    """Raised when a requested identifier cannot be resolved against metadata."""


class UnknownIngestionJobError(InvalidIdentifierError):
    """Raised when the requested ingestion job does not exist."""


class IncompleteIngestionJobError(AnalyticsQueryError, ValueError):
    """Raised when the requested ingestion job is not complete."""


class InvalidAggregationError(AnalyticsQueryError, ValueError):
    """Raised when an aggregation is incompatible with the resolved metadata."""


class InvalidSortError(AnalyticsQueryError, ValueError):
    """Raised when a requested sort target is invalid."""


class InvalidExecutionPlanError(AnalyticsQueryError, ValueError):
    """Raised when an execution plan is invalid for repository execution."""


class DatasetNotAnalyticsReadyError(AnalyticsQueryError, ValueError):
    """Raised when a dataset is not analytics-ready for discovery or query building."""
