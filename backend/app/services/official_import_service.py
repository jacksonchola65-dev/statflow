from __future__ import annotations

import asyncio
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Optional

from app.models.data_source import DatasetRegistry
from app.models.ingestion import IngestionStatus
from app.services.ingestion_persistence_service import (
    IngestionPersistenceService,
)
from app.services.ingestion_profiling_service import (
    IngestionProfilingService,
)
from sqlalchemy.ext.asyncio import AsyncSession


class ImportSource(str, Enum):
    """Source of official dataset imports."""

    ZAMSTATS = "zamstats"
    PACRA = "pacra"
    BANK_OF_ZAMBIA = "bank_of_zambia"
    ZRA = "zra"
    OTHER = "other"


@dataclass(frozen=True)
class ImportData:
    """Raw data returned by an official importer."""

    source: ImportSource
    original_filename: str
    content: bytes
    source_reference: Optional[str] = None


class OfficialDataImporter(ABC):
    """Abstract base class for official dataset importers."""

    @abstractmethod
    async def import_data(self) -> ImportData:
        """Fetch raw bytes, filename, and source metadata for a dataset."""
        raise NotImplementedError


class OfficialImportError(Exception):
    """Raised when an official importer fails to retrieve dataset payload."""


@dataclass(frozen=True)
class ImportResult:
    """Result of an official import orchestration."""

    ingestion_job_id: uuid.UUID
    source: ImportSource
    original_filename: str
    rows_imported: int
    columns_imported: int
    final_status: IngestionStatus


class OfficialImportService:
    """Orchestrates official dataset import using existing profiling and persistence services."""

    def __init__(
        self,
        session: AsyncSession,
        *,
        profiling_service: IngestionProfilingService | None = None,
        persistence_service: IngestionPersistenceService | None = None,
    ) -> None:
        self._session = session
        self._profiling_service = profiling_service or IngestionProfilingService()
        self._persistence_service = persistence_service or IngestionPersistenceService(session)

    async def import_data(
        self,
        importer: OfficialDataImporter,
        dataset_registry: DatasetRegistry,
        *,
        created_by_user_id: Optional[uuid.UUID] = None,
    ) -> ImportResult:
        """Import an official dataset using the pluggable importer implementation."""
        try:
            import_data = await importer.import_data()
        except asyncio.CancelledError:
            # Always allow cancellation to propagate.
            raise
        except Exception as exc:
            raise OfficialImportError("Official importer failed to retrieve dataset.") from exc

        profile = self._profiling_service.profile_dataset(
            filename=import_data.original_filename,
            content=import_data.content,
        )

        persistence_result = await self._persistence_service.persist_profile(
            profile=profile,
            dataset_registry=dataset_registry,
            source_type=import_data.source.value,
            source_reference=import_data.source_reference,
            created_by_user_id=created_by_user_id,
        )

        return ImportResult(
            ingestion_job_id=persistence_result.ingestion_job_id,
            source=import_data.source,
            original_filename=import_data.original_filename,
            rows_imported=persistence_result.rows_inserted,
            columns_imported=persistence_result.columns_inserted,
            final_status=persistence_result.final_status,
        )


async def import_data(
    session: AsyncSession,
    importer: OfficialDataImporter,
    dataset_registry: DatasetRegistry,
    *,
    created_by_user_id: Optional[uuid.UUID] = None,
) -> ImportResult:
    """Convenience wrapper for OfficialImportService.import_data()."""
    service = OfficialImportService(session)
    return await service.import_data(
        importer=importer,
        dataset_registry=dataset_registry,
        created_by_user_id=created_by_user_id,
    )
