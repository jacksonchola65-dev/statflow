from __future__ import annotations

import asyncio
import logging
import os
import re
import socket
from dataclasses import dataclass
from ipaddress import ip_address
from typing import Mapping
from urllib.parse import unquote, urljoin, urlsplit

import httpx

from app.services.official_import_service import ImportData, ImportSource

logger = logging.getLogger(__name__)


class HttpImportError(Exception):
    """Base class for HTTP-based official import failures."""


class UnsafeImportUrlError(HttpImportError):
    """Raised when the import URL is unsafe or disallowed."""


class HttpImportTimeoutError(HttpImportError):
    """Raised when the HTTP request exceeds the configured timeout."""


class HttpImportStatusError(HttpImportError):
    """Raised when the remote service returns an unsuccessful status."""


class HttpImportContentTypeError(HttpImportError):
    """Raised when the response content type is not allowed."""


class HttpImportResponseTooLargeError(HttpImportError):
    """Raised when the response exceeds the configured limit."""


class EmptyHttpImportResponseError(HttpImportError):
    """Raised when the response body is empty."""


class HttpImportConnectionError(HttpImportError):
    """Raised when the transport cannot complete the request."""


@dataclass(frozen=True)
class HttpOfficialImportConfig:
    """Immutable configuration for an HTTP-based official importer."""

    source: ImportSource
    url: str
    original_filename: str | None = None
    source_reference: str | None = None
    timeout_seconds: float = 30.0
    maximum_response_bytes: int = 10_000_000
    allowed_content_types: frozenset[str] | set[str] | None = None
    headers: Mapping[str, str] | None = None

    def __post_init__(self) -> None:
        if self.timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be positive")
        if self.maximum_response_bytes <= 0:
            raise ValueError("maximum_response_bytes must be positive")

        if self.allowed_content_types is not None:
            allowed = frozenset(self.allowed_content_types)
            object.__setattr__(self, "allowed_content_types", allowed)
        else:
            object.__setattr__(self, "allowed_content_types", None)

        if self.headers is not None:
            object.__setattr__(self, "headers", dict(self.headers))
        else:
            object.__setattr__(self, "headers", None)


class HttpOfficialDataImporter:
    """Reusable asynchronous HTTP importer for official datasets."""

    def __init__(
        self,
        *,
        config: HttpOfficialImportConfig,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._config = config
        self._client = client or httpx.AsyncClient()
        self._owns_client = client is None

    async def import_data(self) -> ImportData:
        safe_url = self._validate_url(self._config.url)
        if self._config.headers:
            headers = dict(self._config.headers)
        else:
            headers = {}

        final_url = safe_url
        redirect_count = 0
        max_redirects = 3

        while True:
            try:
                response = await self._request(safe_url, headers=headers)
            except asyncio.CancelledError:
                raise
            except httpx.TimeoutException as exc:
                raise HttpImportTimeoutError(
                    f"Request timed out for {self._safe_host(safe_url)}"
                ) from exc
            except httpx.ConnectError as exc:
                raise HttpImportConnectionError(
                    f"Could not connect to {self._safe_host(safe_url)}"
                ) from exc
            except httpx.HTTPError as exc:
                raise HttpImportConnectionError(
                    f"HTTP transport failure for {self._safe_host(safe_url)}"
                ) from exc

            if 300 <= response.status_code < 400:
                location = response.headers.get("location")
                if not location:
                    raise UnsafeImportUrlError(
                        f"Malformed redirect target for {self._safe_host(safe_url)}"
                    )
                if redirect_count >= max_redirects:
                    raise UnsafeImportUrlError(
                        f"Redirect limit exceeded for {self._safe_host(safe_url)}"
                    )
                redirect_count += 1
                safe_url = self._validate_redirect_target(safe_url, location)
                final_url = safe_url
                continue

            if not 200 <= response.status_code < 300:
                raise HttpImportStatusError(
                    f"Unexpected HTTP status {response.status_code} for {self._safe_host(safe_url)}"
                )

            self._validate_content_type(response)
            body_bytes = await self._read_response_body(response)
            if not body_bytes:
                raise EmptyHttpImportResponseError(
                    f"Response body was empty for {self._safe_host(safe_url)}"
                )

            filename = self._resolve_filename(response, final_url)
            logger.info(
                "Imported official dataset",
                extra={
                    "source": self._config.source.value,
                    "host": self._safe_host(final_url),
                    "status": response.status_code,
                    "bytes": len(body_bytes),
                },
            )
            result = ImportData(
                source=self._config.source,
                original_filename=filename,
                content=body_bytes,
                source_reference=self._config.source_reference,
            )
            if self._owns_client:
                await self._client.aclose()
            return result

    async def _request(self, url: str, *, headers: Mapping[str, str]) -> httpx.Response:
        request_timeout = httpx.Timeout(self._config.timeout_seconds)
        return await self._client.get(
            url,
            headers=headers,
            follow_redirects=False,
            timeout=request_timeout,
        )

    async def _read_response_body(self, response: httpx.Response) -> bytes:
        content_length = response.headers.get("content-length")
        if content_length is not None:
            try:
                parsed_length = int(content_length)
            except ValueError:
                parsed_length = None
            else:
                if parsed_length > self._config.maximum_response_bytes:
                    raise HttpImportResponseTooLargeError(
                        f"Response exceeds configured size for {self._safe_host(str(response.url))}"
                    )

        chunks: list[bytes] = []
        total_bytes = 0
        async for chunk in response.aiter_bytes(chunk_size=8192):
            if not chunk:
                continue
            total_bytes += len(chunk)
            if total_bytes > self._config.maximum_response_bytes:
                raise HttpImportResponseTooLargeError(
                    f"Response exceeds configured size for {self._safe_host(str(response.url))}"
                )
            chunks.append(chunk)

        return b"".join(chunks)

    def _validate_content_type(self, response: httpx.Response) -> None:
        allowed = self._config.allowed_content_types
        if not allowed:
            return

        content_type_header = response.headers.get("content-type")
        if not content_type_header:
            raise HttpImportContentTypeError(
                f"Missing content type for {self._safe_host(str(response.url))}"
            )

        media_type = content_type_header.split(";", 1)[0].strip().lower()
        if media_type not in {allowed_item.lower() for allowed_item in allowed}:
            raise HttpImportContentTypeError(
                f"Unsupported content type {media_type} for {self._safe_host(str(response.url))}"
            )

    def _resolve_filename(self, response: httpx.Response, final_url: str) -> str:
        explicit = self._config.original_filename
        if explicit:
            return self._sanitize_filename(explicit)

        content_disposition = response.headers.get("content-disposition")
        if content_disposition:
            parsed_name = self._parse_content_disposition_filename(content_disposition)
            if parsed_name:
                return self._sanitize_filename(parsed_name)

        parsed_url = urlsplit(final_url)
        if parsed_url.path:
            basename = os.path.basename(parsed_url.path)
            if basename and basename != "/":
                return self._sanitize_filename(basename)

        return self._sanitize_filename("dataset.bin")

    def _parse_content_disposition_filename(self, header_value: str) -> str | None:
        header_value = header_value.strip()
        if not header_value:
            return None
        match = re.search(r'filename\s*=\s*"?([^";]+)"?', header_value, flags=re.IGNORECASE)
        if match:
            return match.group(1)
        return None

    def _sanitize_filename(self, raw_name: str) -> str:
        if not raw_name:
            return "dataset.bin"
        decoded_name = unquote(raw_name).strip()
        if not decoded_name:
            return "dataset.bin"
        base_name = os.path.basename(decoded_name.replace("\\", "/"))
        base_name = base_name.strip(" .")
        if not base_name or base_name in {".", ".."}:
            return "dataset.bin"
        safe_name = re.sub(r"[^A-Za-z0-9._-]+", "_", base_name)
        safe_name = safe_name.strip(" .")
        if not safe_name or safe_name in {".", ".."}:
            return "dataset.bin"
        return safe_name[:255]

    def _validate_url(self, url: str) -> str:
        parsed = urlsplit(url)
        if parsed.scheme.lower() not in {"http", "https"}:
            raise UnsafeImportUrlError("Unsupported URL scheme")
        if parsed.username is not None or parsed.password is not None:
            raise UnsafeImportUrlError("Embedded credentials are not allowed")

        hostname = parsed.hostname
        if not hostname:
            raise UnsafeImportUrlError("URL must include a hostname")

        lowered = hostname.lower()
        if lowered in {"localhost", "::1"}:
            raise UnsafeImportUrlError("Localhost URLs are not allowed")

        try:
            address_infos = socket.getaddrinfo(hostname, None, family=socket.AF_UNSPEC, type=socket.SOCK_STREAM)
        except socket.gaierror as exc:
            raise UnsafeImportUrlError(f"Unable to resolve hostname {self._safe_host(url)}") from exc

        for family, _, _, _, sockaddr in address_infos:
            if family == socket.AF_INET6 and len(sockaddr) >= 1:
                candidate = sockaddr[0]
            elif family == socket.AF_INET and len(sockaddr) >= 1:
                candidate = sockaddr[0]
            else:
                continue
            try:
                address = ip_address(candidate)
            except ValueError:
                continue
            if address.is_loopback or address.is_link_local or address.is_private or address.is_multicast or address.is_unspecified:
                raise UnsafeImportUrlError(f"Unsafe destination address for {self._safe_host(url)}")

        return str(parsed.geturl())

    def _validate_redirect_target(self, current_url: str, location: str) -> str:
        parsed_location = urlsplit(location)
        if not parsed_location.scheme and not parsed_location.netloc:
            target_url = urljoin(current_url, location)
        else:
            target_url = location
        validated_url = self._validate_url(target_url)
        return validated_url

    def _safe_host(self, url: str) -> str:
        try:
            parsed = urlsplit(url)
        except ValueError:
            return "unknown"
        return parsed.hostname or "unknown"
