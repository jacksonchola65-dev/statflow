"""Construction of the internal StatFlow tool registry."""

from __future__ import annotations

from app.db.session import get_db
from app.domain.analytics.dependencies import (
    get_analytics_service,
    get_dataset_discovery_service,
    get_stored_dataset_intelligence_service,
)
from app.services.stored_dataset_intelligence_service import StoredDatasetIntelligenceService
from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from .registry import ToolRegistry
from .registry_handlers import StatFlowToolHandlers, register_statflow_tools


def build_tool_registry(
    *,
    discovery,
    intelligence: StoredDatasetIntelligenceService,
    analytics,
    db: AsyncSession,
) -> ToolRegistry:
    return register_statflow_tools(
        ToolRegistry(),
        StatFlowToolHandlers(discovery, intelligence, analytics, db),
    )


def get_tool_registry(
    db: AsyncSession = Depends(get_db),
    discovery=Depends(get_dataset_discovery_service),
    intelligence: StoredDatasetIntelligenceService = Depends(
        get_stored_dataset_intelligence_service
    ),
    analytics=Depends(get_analytics_service),
) -> ToolRegistry:
    """FastAPI-compatible internal dependency; no public execution route uses it yet."""
    return build_tool_registry(
        discovery=discovery,
        intelligence=intelligence,
        analytics=analytics,
        db=db,
    )
