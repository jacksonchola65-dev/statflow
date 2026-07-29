"""
services/mapped_preview_service.py
================================
Short-lived mapped-preview token store used by MappingExecutionService.

This mirrors the inspection token store pattern used in
`file_inspection_service.py` but stores the results of applying a mapping
configuration (transformed rows + metadata) so the frontend can confirm
before creating persistent datasets.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from app.services.file_inspection_service import TOKEN_TTL
from app.schemas.ingestion_mapping import MappingConfiguration


@dataclass
class _MappedPreviewEntry:
    payload: "CachedMappedPreview"
    created_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


_MAPPED_PREVIEW_STORE: dict[str, _MappedPreviewEntry] = {}


def _store_mapped_preview_token(payload: "CachedMappedPreview") -> str:
    token = str(uuid.uuid4())
    _MAPPED_PREVIEW_STORE[token] = _MappedPreviewEntry(payload=payload)
    return token


class MappedPreviewTokenNotFoundError(Exception):
    pass


class MappedPreviewTokenExpiredError(Exception):
    pass


class MappedPreviewTokenForbiddenError(Exception):
    pass


def _retrieve_mapped_preview_token(token: str, user_id: uuid.UUID) -> "CachedMappedPreview":
    entry = _MAPPED_PREVIEW_STORE.get(token)
    if entry is None:
        raise MappedPreviewTokenNotFoundError("Mapped-preview token not found.")
    if datetime.now(timezone.utc) > entry.created_at + TOKEN_TTL:
        _MAPPED_PREVIEW_STORE.pop(token, None)
        raise MappedPreviewTokenExpiredError("Mapped-preview token expired.")
    if entry.payload.owner_id != user_id:
        raise MappedPreviewTokenForbiddenError("Mapped-preview token does not belong to this user.")
    return entry.payload


def _invalidate_mapped_preview_token(token: str) -> None:
    _MAPPED_PREVIEW_STORE.pop(token, None)


@dataclass(frozen=True)
class CachedMappedPreview:
    mapped_preview_token: str
    transformed_rows: list[dict[str, Any]]
    mapping_configuration: MappingConfiguration
    source_filename: str
    original_headers: list[str]
    owner_id: uuid.UUID
