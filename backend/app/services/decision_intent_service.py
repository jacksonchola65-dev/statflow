from __future__ import annotations

import re
from collections.abc import Sequence

from app.schemas.decision import DecisionMode
from app.schemas.decision_intent import IntentStatus, ParsedDecisionIntent

SUPPORTED_MODEL_ID = "BUSINESS_LOCATION_OPPORTUNITY"


class DecisionIntentInterpreter:
    """Deterministic, provider-free interpretation above the decision engine."""

    _CATEGORY_PATTERNS = (
        ("SUPERMARKET", ("supermarket", "super markets")),
        ("GENERAL_RETAIL", ("general retail", "retail business", "retail store", "shop")),
    )
    _UNSUPPORTED_PATTERNS = (
        "stock",
        "election",
        "person to hire",
        "best person",
        "employee",
    )

    def interpret(
        self,
        text: str,
        *,
        supported_provinces: Sequence[dict[str, str]],
    ) -> ParsedDecisionIntent:
        original = text.strip()
        normalized = re.sub(r"\s+", " ", original.casefold())
        if any(token in normalized for token in self._UNSUPPORTED_PATTERNS):
            return ParsedDecisionIntent(
                original_text=original,
                status=IntentStatus.UNSUPPORTED,
                confidence=0.98,
                unsupported_parts=("Only Business Location Opportunity decisions are supported.",),
            )

        location_intent = any(
            phrase in normalized
            for phrase in (
                "where should",
                "which district",
                "best district",
                "open a",
                "location",
                "locate",
                "where demand",
            )
        )
        if "where should i invest" in normalized or "i want to invest" in normalized:
            location_intent = False
        if not location_intent:
            return ParsedDecisionIntent(
                original_text=original,
                status=IntentStatus.NEEDS_CLARIFICATION,
                confidence=0.35,
                clarification_required=True,
                missing_fields=("decision_type",),
                clarification_questions=(
                    "What decision would you like to make? StatFlow currently supports Business Location Opportunity analysis.",
                ),
            )

        category = next(
            (
                canonical
                for canonical, patterns in self._CATEGORY_PATTERNS
                if any(pattern in normalized for pattern in patterns)
            ),
            None,
        )
        province = self._province_code(normalized, supported_provinces)
        exploratory = any(
            phrase in normalized
            for phrase in ("exploratory", "explore", "look at", "limited analysis")
        )
        questions: list[str] = []
        if category is None:
            questions.append(
                "Which business category would you like to evaluate: supermarket or general retail?"
            )
        if province is None:
            questions.append("Which province would you like to evaluate?")
        if questions:
            return ParsedDecisionIntent(
                original_text=original,
                status=IntentStatus.NEEDS_CLARIFICATION,
                model_id=SUPPORTED_MODEL_ID,
                business_category=category,
                province=province,
                requested_mode=DecisionMode.EXPLORATORY if exploratory else DecisionMode.PRODUCTION,
                confidence=0.78 if category or province else 0.52,
                clarification_required=True,
                missing_fields=tuple(
                    field
                    for field, value in (
                        ("business_category", category),
                        ("province", province),
                    )
                    if value is None
                ),
                clarification_questions=tuple(questions),
            )

        return ParsedDecisionIntent(
            original_text=original,
            status=IntentStatus.SUPPORTED,
            model_id=SUPPORTED_MODEL_ID,
            business_category=category,
            province=province,
            requested_mode=DecisionMode.EXPLORATORY if exploratory else DecisionMode.PRODUCTION,
            confidence=0.98,
        )

    @staticmethod
    def _province_code(text: str, provinces: Sequence[dict[str, str]]) -> str | None:
        for province in provinces:
            code = province["code"].strip().upper()
            name = province["name"].strip().casefold()
            if name in text or code.casefold() in re.findall(r"\b[a-z]{2}\b", text):
                return code
        return None
