import uuid
from typing import Optional

from app.models.indicator import Indicator
from app.repositories.analytics_repository import AnalyticsRepository
from app.schemas.analytics import IndicatorSummaryResponse, ProvinceIndicatorResult
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


class AnalyticsService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._repo = AnalyticsRepository(session)

    async def get_indicator_summary(
        self,
        indicator_id: uuid.UUID,
        reference_year: int,
        dataset_id: Optional[uuid.UUID] = None,
    ) -> IndicatorSummaryResponse:
        # ── Verify indicator exists ────────────────────────────────────────
        result = await self._session.execute(select(Indicator).where(Indicator.id == indicator_id))
        indicator = result.scalar_one_or_none()
        if indicator is None:
            raise HTTPException(
                status_code=404,
                detail=f"Indicator '{indicator_id}' not found.",
            )

        # ── Fetch province-level rows ──────────────────────────────────────
        rows = await self._repo.get_province_indicator_rows(
            indicator_id=indicator_id,
            reference_year=reference_year,
            dataset_id=dataset_id,
        )

        # ── Ambiguity check ───────────────────────────────────────────────
        # When dataset_id is omitted and multiple datasets have data for
        # the same province/year/indicator, the results are ambiguous.
        if dataset_id is None and rows:
            unique_datasets = {row.dataset_id for row in rows}
            if len(unique_datasets) > 1:
                raise HTTPException(
                    status_code=409,
                    detail=(
                        f"Ambiguous data: indicator '{indicator_id}' for year "
                        f"{reference_year} exists in {len(unique_datasets)} datasets "
                        f"({', '.join(str(d) for d in unique_datasets)}). "
                        "Supply dataset_id to resolve the ambiguity."
                    ),
                )

        # ── Build response ────────────────────────────────────────────────
        resolved_dataset_id = dataset_id
        if resolved_dataset_id is None and rows:
            resolved_dataset_id = rows[0].dataset_id

        return IndicatorSummaryResponse(
            indicator_id=indicator_id,
            dataset_id=resolved_dataset_id,
            reference_year=reference_year,
            unit=indicator.unit,
            results=[
                ProvinceIndicatorResult(
                    province_id=row.province_id,
                    province_code=row.province_code,
                    province_name=row.province_name,
                    value=row.value,
                )
                for row in rows
            ],
        )
