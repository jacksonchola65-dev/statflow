from __future__ import annotations

from app.ai.service import StatFlowAssistantService
from app.tools.factory import get_tool_registry
from fastapi import Depends


def get_assistant_service(registry=Depends(get_tool_registry)) -> StatFlowAssistantService:
    return StatFlowAssistantService(registry)
