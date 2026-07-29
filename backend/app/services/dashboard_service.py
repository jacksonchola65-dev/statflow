from __future__ import annotations

import uuid
from typing import Any

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.dashboard import Dashboard
from app.models.dashboard_card import DashboardCard, DashboardCardSize, DashboardVisualizationType
from app.repositories.dashboard_repository import DashboardRepository


class DashboardNotFoundError(Exception):
    """Raised when a dashboard does not exist."""


class DashboardOwnershipError(Exception):
    """Raised when a user tries to modify a dashboard they do not own."""


class DashboardService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._repo = DashboardRepository(session)

    def _build_card_rows(self, cards: list[dict[str, Any]]) -> list[DashboardCard]:
        normalized: list[DashboardCard] = []
        for index, raw in enumerate(cards):
            visualization_type = raw.get("visualization_type") or "bar"
            size = raw.get("size") or "medium"
            card_id = raw.get("id")
            if card_id is None:
                card_id = str(uuid.uuid4())
            elif isinstance(card_id, uuid.UUID):
                card_id = str(card_id)

            normalized.append(
                DashboardCard(
                    id=card_id,
                    title=raw.get("title") or "Visualization card",
                    subtitle=raw.get("subtitle"),
                    visualization_type=DashboardVisualizationType(
                        visualization_type.lower()
                    ),
                    visualization_snapshot=raw.get("visualization_snapshot") or {},
                    size=DashboardCardSize(size.lower()),
                    display_order=int(raw.get("order") or index),
                )
            )
        return normalized

    async def list_dashboards(self, user_id: uuid.UUID) -> list[Dashboard]:
        return await self._repo.list_for_user(user_id)

    async def get_dashboard(self, dashboard_id: uuid.UUID) -> Dashboard:
        dashboard = await self._repo.get_by_id(dashboard_id)
        if dashboard is None:
            raise DashboardNotFoundError("Dashboard not found.")
        return dashboard

    async def create_dashboard(
        self,
        user_id: uuid.UUID,
        title: str,
        description: str | None,
        cards: list[dict[str, Any]],
    ) -> Dashboard:
        dashboard = await self._repo.create(
            owner_id=user_id,
            title=title.strip(),
            description=description.strip() if description else None,
            cards=self._build_card_rows(cards),
        )
        await self._session.flush()
        hydrated_dashboard = await self._repo.get_by_id(dashboard.id)
        assert hydrated_dashboard is not None
        return hydrated_dashboard

    async def update_dashboard(
        self,
        dashboard_id: uuid.UUID,
        user_id: uuid.UUID,
        *,
        title: str | None = None,
        description: str | None = None,
        cards: list[dict[str, Any]] | None = None,
    ) -> Dashboard:
        dashboard = await self._repo.get_by_id(dashboard_id)
        if dashboard is None:
            raise DashboardNotFoundError("Dashboard not found.")
        if dashboard.owner_id != user_id:
            raise DashboardOwnershipError("You do not own this dashboard.")

        if title is not None:
            dashboard.title = title.strip()
        if description is not None:
            dashboard.description = description.strip() if description else None
        if cards is not None:
            await self._session.execute(
                delete(DashboardCard).where(DashboardCard.dashboard_id == dashboard_id)
            )
            dashboard.cards = self._build_card_rows(cards)

        await self._session.flush()
        hydrated_dashboard = await self._repo.get_by_id(dashboard_id)
        assert hydrated_dashboard is not None
        return hydrated_dashboard

    async def delete_dashboard(self, dashboard_id: uuid.UUID, user_id: uuid.UUID) -> None:
        dashboard = await self._repo.get_by_id(dashboard_id)
        if dashboard is None:
            raise DashboardNotFoundError("Dashboard not found.")
        if dashboard.owner_id != user_id:
            raise DashboardOwnershipError("You do not own this dashboard.")
        deleted = await self._repo.delete(dashboard_id)
        assert deleted
        await self._session.flush()
        await self._session.commit()
        self._session.expunge_all()
