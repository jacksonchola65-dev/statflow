"""Optional model provider adapters and deterministic test gateway."""

from __future__ import annotations

import asyncio
import json
from typing import Any

import httpx
from app.core.config import settings

from .contracts import GatewayRequest, GatewayResponse, GatewayToolCall, ModelGateway


class AiProviderError(Exception):
    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


class OpenAiCompatibleGateway(ModelGateway):
    """Minimal REST adapter; provider-specific payloads stay in this module."""

    provider = "openai_compatible"

    async def generate(self, request: GatewayRequest) -> GatewayResponse:
        if not settings.AI_API_KEY or not settings.AI_BASE_URL:
            raise AiProviderError("AI_MISCONFIGURED")
        payload = {
            "model": request.model,
            "messages": [self._message(message) for message in request.messages],
            "tools": request.tools,
            "tool_choice": "auto" if request.tools else "none",
            "max_tokens": request.max_output_tokens,
        }
        try:
            async with httpx.AsyncClient(timeout=settings.AI_TIMEOUT_SECONDS) as client:
                response = await client.post(
                    settings.AI_BASE_URL.rstrip("/") + "/chat/completions",
                    headers={"Authorization": f"Bearer {settings.AI_API_KEY}"},
                    json=payload,
                )
                if response.status_code == 429:
                    raise AiProviderError("MODEL_RATE_LIMITED")
                response.raise_for_status()
                body = response.json()
        except asyncio.TimeoutError as exc:
            raise AiProviderError("MODEL_TIMEOUT") from exc
        except httpx.TimeoutException as exc:
            raise AiProviderError("MODEL_TIMEOUT") from exc
        except AiProviderError:
            raise
        except httpx.HTTPError as exc:
            raise AiProviderError("MODEL_UNAVAILABLE") from exc
        try:
            choice = body["choices"][0]
            message = choice["message"]
            calls = [
                GatewayToolCall(
                    id=item["id"],
                    name=item["function"]["name"],
                    arguments=json.loads(item["function"].get("arguments", "{}")),
                )
                for item in message.get("tool_calls", [])
            ]
            return GatewayResponse(
                text=message.get("content") or "",
                tool_calls=calls,
                finish_reason=choice.get("finish_reason"),
                usage=body.get("usage") or {},
                provider=self.provider,
                model=request.model,
            )
        except (KeyError, IndexError, TypeError, ValueError) as exc:
            raise AiProviderError("INVALID_MODEL_RESPONSE") from exc

    @staticmethod
    def _message(message) -> dict[str, Any]:
        if message.role.value == "tool":
            return {
                "role": "tool",
                "tool_call_id": message.tool_call_id,
                "content": message.content,
            }
        if message.role.value == "assistant" and message.tool_name:
            return {
                "role": "assistant",
                "content": message.content or None,
                "tool_calls": [
                    {
                        "id": message.tool_call_id,
                        "type": "function",
                        "function": {
                            "name": message.tool_name,
                            "arguments": json.dumps(message.tool_arguments or {}),
                        },
                    }
                ],
            }
        return {"role": message.role.value, "content": message.content}


class FakeModelGateway(ModelGateway):
    """Deterministic scripted gateway used by CI and security tests."""

    provider = "fake"

    def __init__(self, responses: list[GatewayResponse] | None = None):
        self.responses = list(responses or [])
        self.requests: list[GatewayRequest] = []

    async def generate(self, request: GatewayRequest) -> GatewayResponse:
        self.requests.append(request)
        if not self.responses:
            return GatewayResponse(
                text="No scripted model response.", provider=self.provider, model=request.model
            )
        return self.responses.pop(0)
