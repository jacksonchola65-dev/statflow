from collections.abc import Callable

from app.domain.decision.models.business_location import (
    BUSINESS_LOCATION_MODEL_ID,
    build_business_location_definition,
    get_business_category_profile,
)

DecisionModelDefinitionFactory = Callable[[], object]


def get_decision_model_definition(model_id: str, *, business_category: str = "GENERAL_RETAIL"):
    if model_id != BUSINESS_LOCATION_MODEL_ID:
        raise KeyError(f"unknown decision model: {model_id}")
    return build_business_location_definition(get_business_category_profile(business_category))
