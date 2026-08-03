"""
repositories/import_template_repository.py
========================================

Data access layer for ImportTemplate persistence.

Follows the StatFlow repository pattern:
- AsyncSession injected via __init__.
- Never commits or rolls back; the caller owns the transaction boundary.
- Returns ORM objects when appropriate.
"""

from __future__ import annotations

import uuid

from app.models.import_template import ImportTemplate
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


class ImportTemplateRepository:
    """Data access for reusable import mapping templates."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        owner_id: uuid.UUID,
        name: str,
        description: str | None,
        source_format: str,
        original_headers: list[str],
        mapping_config: dict,
    ) -> ImportTemplate:
        template = ImportTemplate(
            owner_id=owner_id,
            name=name.strip(),
            description=description,
            source_format=source_format,
            original_headers=original_headers,
            mapping_config=mapping_config,
        )
        self._session.add(template)
        await self._session.flush()
        return template

    async def list_by_owner(
        self, owner_id: uuid.UUID, include_inactive: bool = False
    ) -> list[ImportTemplate]:
        query = select(ImportTemplate).where(ImportTemplate.owner_id == owner_id)
        if not include_inactive:
            query = query.where(ImportTemplate.is_active.is_(True))
        query = query.order_by(ImportTemplate.created_at.desc())
        result = await self._session.execute(query)
        return list(result.scalars().all())

    async def get_by_id(
        self,
        template_id: uuid.UUID,
        owner_id: uuid.UUID,
        include_inactive: bool = False,
    ) -> ImportTemplate | None:
        query = select(ImportTemplate).where(
            ImportTemplate.id == template_id,
            ImportTemplate.owner_id == owner_id,
        )
        if not include_inactive:
            query = query.where(ImportTemplate.is_active.is_(True))
        result = await self._session.execute(query)
        return result.scalar_one_or_none()

    async def update(
        self,
        template: ImportTemplate,
        name: str | None = None,
        description: str | None = None,
        source_format: str | None = None,
        original_headers: list[str] | None = None,
        mapping_config: dict | None = None,
    ) -> ImportTemplate:
        if name is not None:
            template.name = name.strip()
        if description is not None:
            template.description = description
        if source_format is not None:
            template.source_format = source_format
        if original_headers is not None:
            template.original_headers = original_headers
        if mapping_config is not None:
            template.mapping_config = mapping_config
        await self._session.flush()
        return template

    async def deactivate(self, template: ImportTemplate) -> ImportTemplate:
        template.is_active = False
        await self._session.flush()
        return template

    async def name_exists(
        self,
        owner_id: uuid.UUID,
        name: str,
        exclude_id: uuid.UUID | None = None,
    ) -> bool:
        query = select(ImportTemplate.id).where(
            ImportTemplate.owner_id == owner_id,
            ImportTemplate.name == name.strip(),
        )
        if exclude_id is not None:
            query = query.where(ImportTemplate.id != exclude_id)
        result = await self._session.execute(query)
        return result.scalar_one_or_none() is not None
