from __future__ import annotations

import uuid

import pytest
from app.models.user import UserRole
from app.tools import (
    DatasetToolArguments,
    ToolAuthority,
    ToolDefinition,
    ToolExecutionContext,
    ToolRegistry,
    ToolStatus,
)
from app.tools.contracts import RunDatasetAnalysisArguments, RunDecisionArguments
from app.tools.registry import ToolHandlerResult
from app.tools.registry_handlers import StatFlowToolHandlers


def context(role=UserRole.ANALYST):
    return ToolExecutionContext(user_id=uuid.uuid4(), role=role, request_id="registry-test")


async def handler(_context, args):
    return ToolHandlerResult(
        data={"dataset_id": str(args.dataset_id)},
        authority=ToolAuthority.DETERMINISTIC,
        provenance={"source": "test"},
    )


@pytest.mark.asyncio
async def test_registry_registration_discovery_and_execution():
    registry = ToolRegistry()
    registry.register(
        ToolDefinition(
            name="metadata",
            version=1,
            description="metadata",
            arguments_model=DatasetToolArguments,
            handler=handler,
        )
    )
    descriptors = registry.describe_tools(context())
    assert descriptors[0].name == "metadata"
    assert descriptors[0].version == 1
    result = await registry.execute("metadata", {"dataset_id": str(uuid.uuid4())}, context())
    assert result.status is ToolStatus.SUCCESS
    assert result.authority is ToolAuthority.DETERMINISTIC
    assert result.provenance["source"] == "test"


@pytest.mark.asyncio
async def test_registry_rejects_unknown_extra_and_identity_arguments():
    registry = ToolRegistry()
    registry.register(
        ToolDefinition(
            name="metadata",
            version=1,
            description="metadata",
            arguments_model=DatasetToolArguments,
            handler=handler,
        )
    )
    assert (
        await registry.execute("missing", {}, context())
    ).status is ToolStatus.UNSUPPORTED_OPERATION
    assert (
        await registry.execute(
            "metadata", {"dataset_id": str(uuid.uuid4()), "role": "ADMIN"}, context()
        )
    ).status is ToolStatus.INVALID_ARGUMENTS
    assert (await registry.execute("metadata", {}, None)).status is ToolStatus.UNAUTHORIZED


@pytest.mark.asyncio
async def test_registry_permission_aware_discovery_and_duplicate_registration():
    registry = ToolRegistry()
    registry.register(
        ToolDefinition(
            name="admin_tool",
            version=1,
            description="admin",
            arguments_model=DatasetToolArguments,
            handler=handler,
            required_roles=frozenset({UserRole.ADMIN.value}),
        )
    )
    assert registry.describe_tools(context(UserRole.ANALYST)) == []
    assert registry.describe_tools(context(UserRole.ADMIN))[0].name == "admin_tool"
    with pytest.raises(ValueError, match="already registered"):
        registry.register(
            ToolDefinition(
                name="admin_tool",
                version=1,
                description="admin",
                arguments_model=DatasetToolArguments,
                handler=handler,
            )
        )


@pytest.mark.asyncio
async def test_registry_sanitizes_handler_failures():
    async def broken(_context, _args):
        raise RuntimeError("database password=secret")

    registry = ToolRegistry()
    registry.register(
        ToolDefinition(
            name="broken",
            version=1,
            description="broken",
            arguments_model=DatasetToolArguments,
            handler=broken,
        )
    )
    result = await registry.execute("broken", {"dataset_id": str(uuid.uuid4())}, context())
    assert result.status is ToolStatus.EXECUTION_FAILED
    assert result.error_code == "EXECUTION_FAILED"
    assert result.data is None


def test_typed_analysis_arguments_reject_sql_like_identifiers_and_extra_fields():
    with pytest.raises(Exception):
        RunDatasetAnalysisArguments(
            dataset_id=uuid.uuid4(),
            dimension="branch; DROP TABLE dataset_rows",
            aggregation="SUM",
            measure="revenue",
        )
    with pytest.raises(Exception):
        RunDatasetAnalysisArguments(
            dataset_id=uuid.uuid4(),
            aggregation="SUM",
            measure="revenue",
            sql="SELECT * FROM dataset_rows",
        )


@pytest.mark.asyncio
async def test_decision_tool_preserves_insufficient_evidence(monkeypatch):
    class StubDecisionService:
        def __init__(self, _db):
            pass

        async def evaluate(self, **_kwargs):
            return {
                "decision_readiness": "INSUFFICIENT_EVIDENCE",
                "recommendation": None,
                "production_recommendation": False,
                "blockers": ("electricity_access",),
            }

    monkeypatch.setattr("app.tools.registry_handlers.DecisionApiService", StubDecisionService)
    handlers = StatFlowToolHandlers(None, None, None, object())
    result = await handlers.run_decision(
        context(),
        RunDecisionArguments(
            model_id="BUSINESS_LOCATION_OPPORTUNITY",
            province_code="LK",
            business_category="GENERAL_RETAIL",
            mode="PRODUCTION",
        ),
    )
    assert result.status is ToolStatus.INSUFFICIENT_EVIDENCE
    assert result.data["recommendation"] is None
    assert result.data["production_recommendation"] is False
    assert result.authority is ToolAuthority.DECISION_GOVERNED
