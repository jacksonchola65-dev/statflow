from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional, Tuple

from app.semantic.semantic_models import SemanticClassification


@dataclass(frozen=True)
class DetectorInput:
    column_name: str
    values: Tuple[Any, ...] = field(default_factory=tuple)
    inferred_type: Optional[str] = None

    def __post_init__(self):
        # ensure values is immutable tuple
        object.__setattr__(self, "values", tuple(self.values))


@dataclass(frozen=True)
class DetectorResult:
    detector_name: str
    classifications: Tuple[SemanticClassification, ...] = field(default_factory=tuple)

    def __post_init__(self):
        object.__setattr__(self, "classifications", tuple(self.classifications))


class SemanticDetector(ABC):
    @abstractmethod
    def detect(self, input: DetectorInput) -> DetectorResult:
        """Run detection on the provided `DetectorInput` and return a `DetectorResult`.

        Implementations must not mutate input and must return an immutable DetectorResult.
        """
        raise NotImplementedError

    def detect_batch(self, inputs: list[DetectorInput]) -> list[DetectorResult]:
        """Run detection across all inputs in a single pass.

        Default implementation preserves compatibility with single-input detectors.
        """
        return [self.detect(input_obj) for input_obj in inputs]
