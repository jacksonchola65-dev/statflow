from __future__ import annotations

from datetime import date
from enum import Enum
from typing import Protocol

from app.domain.decision.contracts import (
    DecisionAlternative,
    DecisionRequest,
    Evidence,
    IndicatorRequirement,
)
from pydantic import BaseModel, ConfigDict


class EvidenceResolutionStatus(str, Enum):
    RESOLVED = "resolved"
    MISSING = "missing"
    STALE = "stale"
    GEOGRAPHICALLY_INCOMPATIBLE = "geographically_incompatible"
    TEMPORALLY_INCOMPATIBLE = "temporally_incompatible"
    AMBIGUOUS = "ambiguous"


class EvidenceResolution(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    status: EvidenceResolutionStatus
    evidence: Evidence | None = None
    detail: str | None = None


class EvidenceBundle(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    items: tuple[EvidenceResolution, ...]

    @property
    def resolved(self) -> tuple[Evidence, ...]:
        return tuple(item.evidence for item in self.items if item.evidence is not None)


class EvidenceResolver(Protocol):
    async def resolve(
        self,
        requirement: IndicatorRequirement,
        alternative: DecisionAlternative,
        request: DecisionRequest,
        *,
        as_of: date | None = None,
    ) -> EvidenceResolution: ...
