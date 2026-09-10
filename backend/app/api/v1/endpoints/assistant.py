from __future__ import annotations

from app.ai.contracts import AiCapabilityState
from app.ai.dependencies import get_assistant_service
from app.ai.service import AiApplicationError, StatFlowAssistantService
from app.core.dependencies import get_current_user, validate_csrf
from app.models.user import User
from app.schemas.assistant import AssistantQuery, GroundedAssistantResponse
from app.tools.contracts import ToolExecutionContext
from fastapi import APIRouter, Depends, HTTPException, Request, status

router = APIRouter(prefix="/assistant", tags=["assistant"])


@router.post(
    "/query",
    response_model=GroundedAssistantResponse,
    summary="Answer one authenticated StatFlow question",
)
async def assistant_query(
    query: AssistantQuery,
    request: Request,
    current_user: User = Depends(get_current_user),
    _: None = Depends(validate_csrf),
    service: StatFlowAssistantService = Depends(get_assistant_service),
) -> GroundedAssistantResponse:
    context = ToolExecutionContext(
        user_id=current_user.id,
        role=current_user.role,
        request_id=getattr(request.state, "request_id", "assistant-request"),
    )
    try:
        return await service.answer(query, context)
    except AiApplicationError as exc:
        http_status = status.HTTP_503_SERVICE_UNAVAILABLE if exc.state is not AiCapabilityState.AVAILABLE else status.HTTP_502_BAD_GATEWAY
        raise HTTPException(status_code=http_status, detail=exc.code.value) from exc
