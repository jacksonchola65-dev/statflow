from __future__ import annotations

from enum import Enum
from typing import Any

from app.schemas.decision import DecisionMode
from pydantic import BaseModel, Field


class IntentStatus(str, Enum):
    SUPPORTED = "SUPPORTED"
    NEEDS_CLARIFICATION = "NEEDS_CLARIFICATION"
    UNSUPPORTED = "UNSUPPORTED"
    PARSED = "SUPPORTED"
    CLARIFICATION_REQUIRED = "NEEDS_CLARIFICATION"
    UNSUPPORTED_DECISION = "UNSUPPORTED"


class ParsedDecisionIntent(BaseModel):
    original_text: str = Field(min_length=1)
    status: IntentStatus
    model_id: str | None = None
    business_category: str | None = None
    province: str | None = None
    candidate_geography: str | None = "DISTRICT"
    requested_mode: DecisionMode = DecisionMode.PRODUCTION
    extracted_constraints: dict[str, Any] = Field(default_factory=dict)
    confidence: float = Field(ge=0.0, le=1.0)
    clarification_required: bool = False
    clarification_questions: tuple[str, ...] = ()
    missing_fields: tuple[str, ...] = ()
    unsupported_parts: tuple[str, ...] = ()


class DecisionIntentRequest(BaseModel):
    text: str = Field(min_length=1, max_length=2000)


class DecisionIntentResponse(BaseModel):
    intent: ParsedDecisionIntent
