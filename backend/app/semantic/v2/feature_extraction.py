from __future__ import annotations

from typing import Optional, Tuple
from app.semantic.v2.feature_models import LightValueFeatures, ExtendedValueFeatures, ColumnFeatureContext


class FeatureExtractionPipeline:
    """Stateless feature extraction pipeline for a single column.

    Usage:
        FeatureExtractionPipeline.extract(column_name, values_tuple)
    """

    @staticmethod
    def extract(column_name: str, values: Tuple[Optional[str], ...]) -> ColumnFeatureContext:
        if not isinstance(column_name, str):
            raise TypeError("column_name must be a str")
        if not isinstance(values, tuple):
            raise TypeError("values must be a tuple")

        total = len(values)
        null_count = 0
        non_null_values: list[LightValueFeatures] = []
        unique_cleaned: set[str] = set()

        for raw in values:
            if raw is None:
                null_count += 1
                continue

            if not isinstance(raw, str):
                raise TypeError("column values must be str or None")

            cleaned = raw.strip()
            lowered = cleaned.lower()

            is_empty = (cleaned == "")

            parsed_number: Optional[float] = None
            is_integer = False
            is_decimal = False

            if not is_empty:
                try:
                    int_val = int(cleaned)
                except Exception:
                    try:
                        f = float(cleaned)
                    except Exception:
                        parsed_number = None
                    else:
                        parsed_number = float(f)
                        is_decimal = True
                else:
                    parsed_number = float(int_val)
                    is_integer = True

            lv = LightValueFeatures(
                raw_value=raw,
                cleaned_value=cleaned,
                lowered_value=lowered,
                is_empty=is_empty,
                is_integer=is_integer,
                is_decimal=is_decimal,
                parsed_number=parsed_number,
            )

            non_null_values.append(lv)
            unique_cleaned.add(cleaned)

        non_null_count = len(non_null_values)
        unique_count = len(unique_cleaned)

        cardinality_ratio = float(unique_count / non_null_count) if non_null_count > 0 else 0.0
        null_ratio = float(null_count / total) if total > 0 else 0.0

        return ColumnFeatureContext(
            column_name=column_name,
            values=tuple(non_null_values),
            null_count=null_count,
            non_null_count=non_null_count,
            unique_count=unique_count,
            cardinality_ratio=cardinality_ratio,
            null_ratio=null_ratio,
        )


__all__ = ["FeatureExtractionPipeline"]
