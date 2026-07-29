from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple, Optional
import math


def _ensure_tuple_of_str(t, name: str):
    if not isinstance(t, tuple):
        raise TypeError(f"{name} must be a tuple")
    for i, v in enumerate(t):
        if not isinstance(v, str):
            raise TypeError(f"{name}[{i}] must be a str")


@dataclass(frozen=True)
class LightValueFeatures:
    raw_value: str
    cleaned_value: str
    lowered_value: str
    is_empty: bool
    is_integer: bool
    is_decimal: bool
    parsed_number: Optional[float]

    def __post_init__(self):
        if not isinstance(self.raw_value, str):
            raise TypeError("raw_value must be a str")
        if not isinstance(self.cleaned_value, str):
            raise TypeError("cleaned_value must be a str")
        if not isinstance(self.lowered_value, str):
            raise TypeError("lowered_value must be a str")
        if not isinstance(self.is_empty, bool):
            raise TypeError("is_empty must be a bool")
        if not isinstance(self.is_integer, bool):
            raise TypeError("is_integer must be a bool")
        if not isinstance(self.is_decimal, bool):
            raise TypeError("is_decimal must be a bool")
        if self.parsed_number is not None and not isinstance(self.parsed_number, float):
            raise TypeError("parsed_number must be a float or None")


@dataclass(frozen=True)
class ExtendedValueFeatures:
    tokens: Tuple[str, ...]
    character_count: int
    digit_count: int
    alpha_count: int

    def __post_init__(self):
        _ensure_tuple_of_str(self.tokens, "tokens")
        for name in ("character_count", "digit_count", "alpha_count"):
            val = getattr(self, name)
            if not isinstance(val, int) or val < 0:
                raise ValueError(f"{name} must be a non-negative int")

    @staticmethod
    def from_light(light: "LightValueFeatures") -> "ExtendedValueFeatures":
        cleaned = light.cleaned_value
        lowered = light.lowered_value
        tokens = tuple(lowered.split())
        character_count = len(cleaned)
        digit_count = sum(1 for c in cleaned if c.isdigit())
        alpha_count = sum(1 for c in cleaned if c.isalpha())
        return ExtendedValueFeatures(
            tokens=tokens,
            character_count=character_count,
            digit_count=digit_count,
            alpha_count=alpha_count,
        )


@dataclass(frozen=True)
class ColumnFeatureContext:
    column_name: str
    values: Tuple[LightValueFeatures, ...]
    null_count: int
    non_null_count: int
    unique_count: int
    cardinality_ratio: float
    null_ratio: float

    def __post_init__(self):
        if not isinstance(self.column_name, str):
            raise TypeError("column_name must be a str")
        if not isinstance(self.values, tuple):
            raise TypeError("values must be a tuple of LightValueFeatures")
        for i, v in enumerate(self.values):
            if not isinstance(v, LightValueFeatures):
                raise TypeError(f"values[{i}] must be a LightValueFeatures")

        for name in ("null_count", "non_null_count", "unique_count"):
            val = getattr(self, name)
            if not isinstance(val, int) or val < 0:
                raise ValueError(f"{name} must be a non-negative int")

        # non_null_count must equal len(values)
        if self.non_null_count != len(self.values):
            raise ValueError("non_null_count must equal the number of provided values")

        if self.unique_count > self.non_null_count:
            raise ValueError("unique_count must not exceed non_null_count")

        if not isinstance(self.cardinality_ratio, float) or math.isnan(self.cardinality_ratio):
            raise TypeError("cardinality_ratio must be a float")
        if not isinstance(self.null_ratio, float) or math.isnan(self.null_ratio):
            raise TypeError("null_ratio must be a float")

        if not (0.0 <= self.cardinality_ratio <= 1.0):
            raise ValueError("cardinality_ratio must be between 0.0 and 1.0")
        if not (0.0 <= self.null_ratio <= 1.0):
            raise ValueError("null_ratio must be between 0.0 and 1.0")

        total = self.non_null_count + self.null_count
        # validate ratio consistency
        if total == 0:
            if self.null_ratio != 0.0:
                raise ValueError("null_ratio must be 0.0 when there are no values and no nulls")
        else:
            expected_null_ratio = self.null_count / total
            if not math.isclose(self.null_ratio, expected_null_ratio, rel_tol=0.0, abs_tol=1e-12):
                raise ValueError("null_ratio inconsistent with null_count and non_null_count")

        if self.non_null_count == 0:
            if self.cardinality_ratio != 0.0:
                raise ValueError("cardinality_ratio must be 0.0 when there are no non-null values")
        else:
            expected_card = self.unique_count / self.non_null_count
            if not math.isclose(self.cardinality_ratio, expected_card, rel_tol=0.0, abs_tol=1e-12):
                raise ValueError("cardinality_ratio inconsistent with unique_count and non_null_count")
