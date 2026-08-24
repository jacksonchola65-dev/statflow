from __future__ import annotations

from app.core.dependencies import get_current_user, validate_csrf
from app.db.session import get_db
from app.domain.decision import BusinessLocationMode
from app.domain.decision.models.business_location import get_business_category_profile
from app.domain.decision.partnership import (
    build_partnership_requirements,
    partnership_requirements_for_partner,
    readiness_scenario,
)
from app.models.province import Province
from app.models.user import User
from app.schemas.decision import (
    DecisionEvaluationRequest,
    DecisionEvaluationResponse,
    DecisionModelDetailsResponse,
    DecisionModelListResponse,
    DecisionModelSummary,
    PartnershipRequirementsResponse,
    PartnershipScenarioResponse,
)
from app.schemas.decision_intent import DecisionIntentRequest, DecisionIntentResponse
from app.services.decision_api_service import DecisionApiService, model_summary
from app.services.decision_intent_service import DecisionIntentInterpreter
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

router = APIRouter(prefix="/decisions", tags=["decisions"])


@router.post(
    "/interpret",
    response_model=DecisionIntentResponse,
    summary="Interpret a supported natural-language decision",
    dependencies=[Depends(validate_csrf)],
)
async def interpret_decision(
    request: DecisionIntentRequest,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
) -> DecisionIntentResponse:
    rows = await db.execute(select(Province.code, Province.name).order_by(Province.code))
    provinces = tuple({"code": code, "name": name} for code, name in rows.all())
    intent = DecisionIntentInterpreter().interpret(request.text, supported_provinces=provinces)
    return DecisionIntentResponse(intent=intent)


@router.get("/models", response_model=DecisionModelListResponse, summary="List decision models")
async def list_decision_models(_: User = Depends(get_current_user)) -> DecisionModelListResponse:
    return DecisionModelListResponse(models=(DecisionModelSummary.model_validate(model_summary()),))


@router.get(
    "/models/{model_id}",
    response_model=DecisionModelDetailsResponse,
    summary="Get decision model details",
)
async def get_decision_model(
    model_id: str, _: User = Depends(get_current_user)
) -> DecisionModelDetailsResponse:
    if model_id != "BUSINESS_LOCATION_OPPORTUNITY":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Decision model not found."
        )
    return DecisionModelDetailsResponse.model_validate(model_summary())


@router.post(
    "/evaluate",
    response_model=DecisionEvaluationResponse,
    summary="Evaluate a registered decision model",
    dependencies=[Depends(validate_csrf)],
)
async def evaluate_decision(
    request: DecisionEvaluationRequest,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
) -> DecisionEvaluationResponse:
    result = await DecisionApiService(db).evaluate(
        model_id=request.model_id,
        province_code=request.province,
        mode=(
            BusinessLocationMode.DECISION_READY
            if request.mode.value == "PRODUCTION"
            else BusinessLocationMode.EXPLORATORY
        ),
        business_category=request.business_category,
        reference_year=request.reference_year,
        criterion_weights=request.criterion_weights,
    )
    return DecisionEvaluationResponse.model_validate(result)


@router.post(
    "/business-location",
    response_model=DecisionEvaluationResponse,
    summary="Evaluate the Business Location Opportunity model",
    dependencies=[Depends(validate_csrf)],
)
async def evaluate_business_location(
    request: DecisionEvaluationRequest,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
) -> DecisionEvaluationResponse:
    return await evaluate_decision(request, db, _)


@router.get(
    "/partnerships",
    response_model=PartnershipRequirementsResponse,
    summary="List institutional evidence partnership requirements",
)
async def list_partnership_requirements(
    partner: str | None = None, _: User = Depends(get_current_user)
) -> PartnershipRequirementsResponse:
    profile = get_business_category_profile("SUPERMARKET")
    requirements = (
        partnership_requirements_for_partner(profile, partner)
        if partner
        else build_partnership_requirements(profile)
    )
    return PartnershipRequirementsResponse(
        model_id="BUSINESS_LOCATION_OPPORTUNITY",
        model_version="business-location-v1",
        requirements=tuple(
            {
                **item.model_dump(),
                "required_geography": item.required_geography.value,
                "preferred_geography": item.preferred_geography.value,
                "current_availability_state": item.current_availability_state.value,
                "blocker_categories": tuple(reason.value for reason in item.blocker_categories),
            }
            for item in requirements
        ),
    )


@router.get(
    "/partnerships/scenario/{criterion_id}",
    response_model=PartnershipScenarioResponse,
    summary="Calculate readiness impact without creating a recommendation",
)
async def get_partnership_scenario(
    criterion_id: str, _: User = Depends(get_current_user)
) -> PartnershipScenarioResponse:
    try:
        scenario = readiness_scenario(get_business_category_profile("SUPERMARKET"), criterion_id)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    return PartnershipScenarioResponse.model_validate(scenario.model_dump())
