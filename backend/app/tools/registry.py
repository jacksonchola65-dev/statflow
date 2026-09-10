"""Internal, provider-neutral registry for governed StatFlow capabilities."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from time import perf_counter
from typing import Any, Awaitable, Callable

from pydantic import BaseModel, ValidationError

from .contracts import (
    ToolAuthority,
    ToolDescriptor,
    ToolExecutionContext,
    ToolResult,
    ToolStatus,
)

logger = logging.getLogger(__name__)


class ToolExecutionError(Exception):
    """Safe, expected tool failure with no implementation detail exposure."""

    def __init__(self, status: ToolStatus, error_code: str) -> None:
        super().__init__(error_code)
        self.status = status
        self.error_code = error_code


@dataclass(frozen=True)
class ToolHandlerResult:
    data: Any
    authority: ToolAuthority
    warnings: tuple[str, ...] = ()
    provenance: dict[str, Any] | None = None
    status: ToolStatus = ToolStatus.SUCCESS
    error_code: str | None = None


ToolHandler = Callable[[ToolExecutionContext, BaseModel], Awaitable[ToolHandlerResult]]


@dataclass(frozen=True)
class ToolDefinition:
    name: str
    version: int
    description: str
    arguments_model: type[BaseModel]
    handler: ToolHandler
    required_roles: frozenset[str] = frozenset()
    read_only: bool = True
    max_result_rows: int | None = None

    def descriptor(self) -> ToolDescriptor:
        return ToolDescriptor(
            name=self.name,
            version=self.version,
            description=self.description,
            input_schema=self.arguments_model.model_json_schema(),
            required_permissions=sorted(self.required_roles),
            read_only=self.read_only,
            max_result_rows=self.max_result_rows,
        )


class ToolRegistry:
    """Register, discover, validate, and execute internal governed tools."""

    def __init__(self) -> None:
        self._tools: dict[str, ToolDefinition] = {}

    def register(self, tool: ToolDefinition) -> None:
        if tool.name in self._tools:
            raise ValueError(f"tool already registered: {tool.name}")
        self._tools[tool.name] = tool

    def describe_tools(self, context: ToolExecutionContext | None) -> list[ToolDescriptor]:
        if context is None:
            return []
        return [
            tool.descriptor()
            for tool in self._tools.values()
            if not tool.required_roles or context.role.value in tool.required_roles
        ]

    async def execute(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        context: ToolExecutionContext | None,
    ) -> ToolResult:
        started = perf_counter()
        tool = self._tools.get(tool_name)
        if tool is None:
            return self._failure(tool_name, ToolStatus.UNSUPPORTED_OPERATION, "UNKNOWN_TOOL", started)
        if context is None:
            return self._failure(tool.name, ToolStatus.UNAUTHORIZED, "AUTHENTICATION_REQUIRED", started, tool.version)
        if tool.required_roles and context.role.value not in tool.required_roles:
            return self._failure(tool.name, ToolStatus.FORBIDDEN, "INSUFFICIENT_PERMISSIONS", started, tool.version)

        try:
            parsed = tool.arguments_model.model_validate(arguments)
        except ValidationError:
            return self._failure(tool.name, ToolStatus.INVALID_ARGUMENTS, "INVALID_ARGUMENTS", started, tool.version)

        try:
            result = await tool.handler(context, parsed)
        except ToolExecutionError as exc:
            return self._failure(tool.name, exc.status, exc.error_code, started, tool.version)
        except Exception:
            logger.exception(
                "Internal tool execution failed",
                extra={"tool_name": tool.name, "tool_version": tool.version, "request_id": context.request_id},
            )
            return self._failure(tool.name, ToolStatus.EXECUTION_FAILED, "EXECUTION_FAILED", started, tool.version)

        return ToolResult(
            tool_name=tool.name,
            tool_version=tool.version,
            status=result.status,
            data=result.data,
            warnings=list(result.warnings),
            provenance=result.provenance or {},
            authority=result.authority,
            execution_metadata={
                "request_id": context.request_id,
                "user_id": str(context.user_id),
                "duration_ms": round((perf_counter() - started) * 1000, 2),
                "read_only": tool.read_only,
            },
            error_code=result.error_code,
        )

    @staticmethod
    def _failure(
        name: str,
        status: ToolStatus,
        error_code: str,
        started: float,
        version: int = 1,
    ) -> ToolResult:
        return ToolResult(
            tool_name=name,
            tool_version=version,
            status=status,
            authority=ToolAuthority.DETERMINISTIC,
            error_code=error_code,
            execution_metadata={"duration_ms": round((perf_counter() - started) * 1000, 2)},
        )
