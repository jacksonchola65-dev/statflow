from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class DashboardCardSchema(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID | str
    title: str
    subtitle: str | None = None
    visualization_type: Literal["kpi", "bar", "line", "area", "pie"] = "bar"
    size: Literal["small", "medium", "large"] = "medium"
    order: int = Field(default=0, ge=0)
    visualization_snapshot: dict[str, Any] | None = None

    @field_validator("title")
    @classmethod
    def normalize_title(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("title must not be blank")
        return normalized

    @field_validator("visualization_snapshot")
    @classmethod
    def validate_snapshot(cls, value: dict[str, Any] | None) -> dict[str, Any] | None:
        if value is None:
            return None
        if not isinstance(value, dict):
            raise ValueError("visualization_snapshot must be a JSON object")
        if any(key in {"token", "session", "password", "secret", "authorization", "cookie"} for key in value):
            raise ValueError("visualization_snapshot contains disallowed sensitive keys")
        return value

    @classmethod
    def from_attributes(cls, obj):
        payload = super().from_attributes(obj)
        if isinstance(obj, dict):
            return payload
        payload["order"] = getattr(obj, "order", getattr(obj, "display_order", payload.get("order", 0)))
        payload["visualization_type"] = getattr(
            obj,
            "visualization_type_value",
            getattr(obj, "visualization_type", payload.get("visualization_type")),
        )
        return payload


class DashboardCreateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=500)
    cards: list[DashboardCardSchema] = Field(default_factory=list)

    @field_validator("title")
    @classmethod
    def normalize_title(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("title must not be blank")
        return normalized

    @model_validator(mode="after")
    def validate_dashboard_cards(self) -> "DashboardCreateRequest":
        card_ids = [card.id for card in self.cards]
        if len(card_ids) != len(set(card_ids)):
            raise ValueError("duplicate card ids are not allowed")

        orders = [card.order for card in self.cards]
        if len(orders) != len(set(orders)):
            raise ValueError("duplicate display orders are not allowed")

        return self


class DashboardUpdateRequest(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=120)
    description: str | None = Field(default=None, max_length=500)
    cards: list[DashboardCardSchema] | None = None

    @field_validator("title")
    @classmethod
    def normalize_title(cls, value: str | None) -> str | None:
        if value is None:
            return value
        normalized = value.strip()
        if not normalized:
            raise ValueError("title must not be blank")
        return normalized

    @model_validator(mode="after")
    def validate_dashboard_cards(self) -> "DashboardUpdateRequest":
        if self.cards is None:
            return self
        card_ids = [card.id for card in self.cards]
        if len(card_ids) != len(set(card_ids)):
            raise ValueError("duplicate card ids are not allowed")

        orders = [card.order for card in self.cards]
        if len(orders) != len(set(orders)):
            raise ValueError("duplicate display orders are not allowed")

        return self


class DashboardResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    owner_id: uuid.UUID
    title: str
    description: str | None = None
    cards: list[DashboardCardSchema]
    created_at: datetime
    updated_at: datetime


class DashboardListResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    dashboards: list[DashboardResponse]
    total: int
