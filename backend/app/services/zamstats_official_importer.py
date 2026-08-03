from __future__ import annotations

from typing import Mapping

from app.core.config import settings
from app.services.http_official_data_importer import (
    HttpOfficialDataImporter,
    HttpOfficialImportConfig,
)
from app.services.official_import_service import ImportData, ImportSource


class ZamstatsOfficialDataImporter:
    """Thin ZAMSTATS-specific importer that delegates transport to the reusable adapter."""

    DEFAULT_SOURCE_REFERENCE = "https://www.zamstats.gov.zm/"

    def __init__(
        self,
        *,
        adapter: HttpOfficialDataImporter | None = None,
        url: str | None = None,
        source_reference: str | None = None,
        timeout_seconds: float = 10.0,
        maximum_response_bytes: int = 5 * 1024 * 1024,
        allowed_content_types: frozenset[str] | set[str] | tuple[str, ...] | None = None,
        headers: Mapping[str, str] | None = None,
    ) -> None:
        self._adapter = adapter
        self._url = url
        self._source_reference = source_reference or self.DEFAULT_SOURCE_REFERENCE
        self._timeout_seconds = timeout_seconds
        self._maximum_response_bytes = maximum_response_bytes
        self._allowed_content_types = allowed_content_types or frozenset(
            {
                "text/csv",
                "application/csv",
                "application/vnd.ms-excel",
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                "application/json",
            }
        )
        self._headers = headers

    async def import_data(self) -> ImportData:
        if self._adapter is None:
            resolved_url = self._resolve_url()
            config = HttpOfficialImportConfig(
                source=ImportSource.ZAMSTATS,
                url=resolved_url,
                original_filename=None,
                source_reference=self._source_reference,
                timeout_seconds=self._timeout_seconds,
                maximum_response_bytes=self._maximum_response_bytes,
                allowed_content_types=self._allowed_content_types,
                headers=self._headers,
            )
            self._adapter = HttpOfficialDataImporter(config=config)

        return await self._adapter.import_data()

    def _resolve_url(self) -> str:
        if self._url:
            return self._url
        configured_url = getattr(settings, "ZAMSTATS_DATASET_URL", None)
        if configured_url:
            return configured_url
        raise ValueError("ZAMSTATS dataset URL must be configured before execution")
