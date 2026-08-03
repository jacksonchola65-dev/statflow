"""Semantic v2 feature models package.

This package is intentionally lightweight and contains only immutable feature dataclasses.
"""

from .feature_models import ColumnFeatureContext, ExtendedValueFeatures, LightValueFeatures

# Backwards-compatibility alias
ValueFeatureSet = LightValueFeatures

__all__ = ["LightValueFeatures", "ExtendedValueFeatures", "ColumnFeatureContext", "ValueFeatureSet"]
