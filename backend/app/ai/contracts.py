"""Provider-neutral model gateway and grounded response contracts."""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class AiCapabilityState(str, Enum):
    AVAILABLE = "AVAILABLE"
    DISABLED = "DISABLED"
    MISCONFIGURED = "MISCONFIGURED"


class AiErrorCode(str, Enum):
    AI_DISABLED = "AI_DISABLED"
    AI_MISCONFIGURED = "AI_MISCONFIGURED"
    MODEL_TIMEOUT = "MODEL_TIMEOUT"
    MODEL_UNAVAILABLE = "MODEL_UNAVAILABLE"
    MODEL_RATE_LIMITED = "MODEL_RATE_LIMITED"
    INVALID_MODEL_RESPONSE = "INVALID_MODEL_RESPONSE"
    TOOL_LIMIT_EXCEEDED = "TOOL_LIMIT_EXCEEDED"
    CONTEXT_LIMIT_EXCEEDED = "CONTEXT_LIMIT_EXCEEDED"
    OUTPUT_POLICY_BLOCKED = "OUTPUT_POLICY_BLOCKED"
    ORCHESTRATION_FAILED = "ORCHESTRATION_FAILED"


class MessageRole(str, Enum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"
    TOOL = "tool"


class ClaimClass(str, Enum):
    GENERAL_EXPLANATION = "GENERAL_EXPLANATION"
    TOOL_DERIVED_FACT = "TOOL_DERIVED_FACT"
    DECISION_RESULT = "DECISION_RESULT"
    EXPLORATORY_RESULT = "EXPLORATORY_RESULT"
    UNSUPPORTED_CLAIM = "UNSUPPORTED_CLAIM"


class GatewayMessage(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: MessageRole
    content: str = ""
    tool_call_id: str | None = None
    tool_name: str | None = None
    tool_arguments: dict[str, Any] | None = None


class GatewayToolCall(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    arguments: dict[str, Any]


class GatewayRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    messages: list[GatewayMessage]
    tools: list[dict[str, Any]] = Field(default_factory=list)
    model: str
    max_output_tokens: int = Field(ge=1, le=4096)
    request_id: str


class GatewayResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = ""
    tool_calls: list[GatewayToolCall] = Field(default_factory=list)
    finish_reason: str | None = None
    usage: dict[str, int] = Field(default_factory=dict)
    provider: str
    model: str
    provider_metadata: dict[str, Any] = Field(default_factory=dict)


class GroundingReference(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tool_name: str
    status: str
    authority: str
    provenance: dict[str, Any] = Field(default_factory=dict)


class GroundedAssistantResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str
    claim_class: ClaimClass
    grounding: list[GroundingReference] = Field(default_factory=list)
    status: str = "SUCCESS"
    error_code: AiErrorCode | None = None
    capability_state: AiCapabilityState
    execution_metadata: dict[str, Any] = Field(default_factory=dict)


class AssistantQuery(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: str = Field(min_length=1, max_length=4000)
    current_page: str | None = Field(default=None, max_length=200)
    dataset_id: str | None = Field(default=None, max_length=100)


class ModelGateway:
    """Canonical provider-neutral gateway interface."""

    async def generate(self, request: GatewayRequest) -> GatewayResponse:
        raise NotImplementedError
