from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class DecisionMode(str, Enum):
    PRODUCTION = "PRODUCTION"
    EXPLORATORY = "EXPLORATORY"


class DecisionEvaluationRequest(BaseModel):
    model_id: str = Field(default="BUSINESS_LOCATION_OPPORTUNITY", min_length=1)
    province: str = Field(min_length=1, description="Canonical province code, for example LP.")
    mode: DecisionMode
    business_category: str = Field(default="GENERAL_RETAIL", min_length=1)
    reference_year: int | None = Field(default=2022, ge=1900, le=2100)
    criterion_weights: dict[str, float] = Field(default_factory=dict)


class DecisionModelSummary(BaseModel):
    model_id: str
    version: str
    name: str
    description: str
    geographic_level: str
    supported_modes: tuple[DecisionMode, ...]
    supported_business_categories: tuple[str, ...]
    readiness_percentage: float
    production_ready: bool
    criteria: tuple[dict[str, Any], ...]
    limitations: tuple[str, ...]


class DecisionModelListResponse(BaseModel):
    models: tuple[DecisionModelSummary, ...]


class DecisionModelDetailsResponse(DecisionModelSummary):
    evidence_backlog: tuple[dict[str, Any], ...]
    methodology_versions: dict[str, str]


class DecisionEvaluationResponse(BaseModel):
    run_id: str
    model_id: str
    model_version: str
    mode: DecisionMode
    exploratory_designation: str
    persisted: bool
    province: str
    decision_readiness: str
    model_readiness_percentage: float
    production_recommendation: bool
    recommendation: dict[str, Any] | None
    candidates: tuple[dict[str, Any], ...]
    evidence: tuple[dict[str, Any], ...]
    criterion_scores: tuple[dict[str, Any], ...]
    evidence_coverage: tuple[dict[str, Any], ...]
    criterion_readiness: tuple[dict[str, Any], ...]
    confidence: dict[str, Any]
    sensitivity: dict[str, Any] | None
    ties: dict[str, Any]
    blockers: tuple[str, ...]
    blocker_reasons: tuple[dict[str, Any], ...]
    limitations: tuple[str, ...]
    explanation: dict[str, Any]
    evidence_backlog: tuple[dict[str, Any], ...]
    methodology_versions: dict[str, str]


class PartnershipRequirementResponse(BaseModel):
    criterion_id: str
    decision_model_id: str
    business_categories: tuple[str, ...]
    title: str
    description: str
    required_geography: str
    preferred_geography: str
    coverage_requirement: str
    freshness_requirement: str
    temporal_requirement: str
    preferred_source_institution: str
    alternative_source_institutions: tuple[str, ...]
    authority_tier_required: str
    expected_data_format: str
    current_availability_state: str
    blocker_categories: tuple[str, ...]
    production_gate_condition: str
    limitations: tuple[str, ...]
    contact_status: str
    methodology_implications: str
    configured_weight: float
    current_readiness_impact_percentage: float
    projected_readiness_percentage: float


class PartnershipRequirementsResponse(BaseModel):
    model_id: str
    model_version: str
    requirements: tuple[PartnershipRequirementResponse, ...]


class PartnershipScenarioResponse(BaseModel):
    criterion_id: str
    current_readiness_percentage: float
    projected_readiness_percentage: float
    recommendation_allowed: bool
    note: str
