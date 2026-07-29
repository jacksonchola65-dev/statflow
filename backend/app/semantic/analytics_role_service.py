from typing import Tuple

from .analytics_role_models import (
    AnalyticsRoleProfile,
    DimensionCandidate,
    MeasureCandidate,
)


class AnalyticsRoleService:
    @staticmethod
    def compose(
        measure_candidates: Tuple[MeasureCandidate, ...],
        dimension_candidates: Tuple[DimensionCandidate, ...],
    ) -> AnalyticsRoleProfile:
        if not isinstance(measure_candidates, tuple):
            raise TypeError("measure_candidates must be a tuple of MeasureCandidate")
        if not isinstance(dimension_candidates, tuple):
            raise TypeError("dimension_candidates must be a tuple of DimensionCandidate")

        for m in measure_candidates:
            if not isinstance(m, MeasureCandidate):
                raise TypeError("measure_candidates must contain MeasureCandidate instances")

        for d in dimension_candidates:
            if not isinstance(d, DimensionCandidate):
                raise TypeError("dimension_candidates must contain DimensionCandidate instances")

        return AnalyticsRoleProfile(
            measure_candidates=measure_candidates,
            dimension_candidates=dimension_candidates,
        )
