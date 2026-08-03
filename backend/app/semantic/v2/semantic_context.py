from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple

from app.semantic.v2.feature_models import ColumnFeatureContext


@dataclass(frozen=True)
class RegexIndex:
    patterns: Tuple[str, ...] = ()


@dataclass(frozen=True)
class DictionaryIndex:
    entries: Tuple[str, ...] = ()


@dataclass(frozen=True)
class SemanticContext:
    columns: Tuple[ColumnFeatureContext, ...]
    regex_index: RegexIndex = RegexIndex()
    dictionary_index: DictionaryIndex = DictionaryIndex()

    # derived fields
    column_count: int = 0
    total_values: int = 0
    total_nulls: int = 0
    total_non_nulls: int = 0

    def __post_init__(self):
        if not isinstance(self.columns, tuple):
            raise TypeError("columns must be a tuple of ColumnFeatureContext")
        names = []
        col_count = 0
        total_vals = 0
        total_nulls = 0
        total_non_nulls = 0
        for i, c in enumerate(self.columns):
            if not hasattr(c, "column_name"):
                raise TypeError(f"columns[{i}] is not a ColumnFeatureContext-like object")
            name = c.column_name
            if name in names:
                raise ValueError(f"duplicate column name '{name}' not allowed")
            names.append(name)
            col_count += 1
            total_nulls += int(getattr(c, "null_count", 0))
            total_non_nulls += int(getattr(c, "non_null_count", 0))
            total_vals += int(getattr(c, "null_count", 0)) + int(getattr(c, "non_null_count", 0))

        # object is frozen; use object.__setattr__ for derived fields
        object.__setattr__(self, "column_count", col_count)
        object.__setattr__(self, "total_values", total_vals)
        object.__setattr__(self, "total_nulls", total_nulls)
        object.__setattr__(self, "total_non_nulls", total_non_nulls)

    def get_column(self, index: int) -> ColumnFeatureContext:
        if not isinstance(index, int):
            raise TypeError("index must be int")
        if index < 0 or index >= len(self.columns):
            raise IndexError("column index out of range")
        return self.columns[index]

    def get_column_by_name(self, name: str) -> ColumnFeatureContext:
        if not isinstance(name, str):
            raise TypeError("name must be str")
        for c in self.columns:
            if c.column_name == name:
                return c
        raise KeyError(f"column '{name}' not found")


__all__ = ["SemanticContext", "RegexIndex", "DictionaryIndex"]
