"""
services/import_template_service.py
===================================

Application service for ImportTemplate lifecycle operations.

This service validates mapping configuration payloads before persistence and
returns the created template entity. It follows the StatFlow service pattern:
- Stateless; a new instance may be created per request.
- Never commits or rolls back; the caller owns the transaction boundary.
"""

from __future__ import annotations

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.import_template import ImportTemplate
from app.repositories.import_template_repository import ImportTemplateRepository
from app.schemas.ingestion_mapping import ImportTemplateCreateRequest


class ImportTemplateService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._repo = ImportTemplateRepository(session)

    async def create_template(
        self,
        owner_id: uuid.UUID,
        payload: ImportTemplateCreateRequest,
    ) -> ImportTemplate:
        if await self._repo.name_exists(owner_id, payload.name):
            raise ValueError(
                f"Import template with name '{payload.name}' already exists."
            )

        return await self._repo.create(
            owner_id=owner_id,
            name=payload.name,
            description=payload.description,
            source_format=payload.source_format,
            original_headers=payload.original_headers,
            mapping_config=payload.mapping_config.model_dump(),
        )

    async def list_templates(
        self,
        owner_id: uuid.UUID,
        include_inactive: bool = False,
    ) -> list[ImportTemplate]:
        return await self._repo.list_by_owner(owner_id, include_inactive=include_inactive)

    async def get_template(
        self,
        template_id: uuid.UUID,
        owner_id: uuid.UUID,
        include_inactive: bool = False,
    ) -> ImportTemplate | None:
        return await self._repo.get_by_id(template_id, owner_id, include_inactive=include_inactive)

    async def update_template(
        self,
        template_id: uuid.UUID,
        owner_id: uuid.UUID,
        payload: 'ImportTemplateUpdateRequest',
    ) -> ImportTemplate:
        template = await self._repo.get_by_id(template_id, owner_id)
        if template is None:
            raise LookupError(f"Import template with id {template_id} not found.")

        if payload.name and await self._repo.name_exists(owner_id, payload.name, exclude_id=template.id):
            raise ValueError(
                f"Import template with name '{payload.name}' already exists."
            )

        return await self._repo.update(
            template=template,
            name=payload.name,
            description=payload.description,
            source_format=payload.source_format,
            original_headers=payload.original_headers,
            mapping_config=payload.mapping_config.model_dump() if payload.mapping_config is not None else None,
        )

    async def deactivate_template(
        self,
        template_id: uuid.UUID,
        owner_id: uuid.UUID,
    ) -> ImportTemplate:
        template = await self._repo.get_by_id(template_id, owner_id)
        if template is None:
            raise LookupError(f"Import template with id {template_id} not found.")
        return await self._repo.deactivate(template)
