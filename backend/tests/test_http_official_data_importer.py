from __future__ import annotations

import socket

import httpx
import pytest
from app.services.http_official_data_importer import (
    EmptyHttpImportResponseError,
    HttpImportContentTypeError,
    HttpImportResponseTooLargeError,
    HttpImportStatusError,
    HttpImportTimeoutError,
    HttpOfficialDataImporter,
    HttpOfficialImportConfig,
    UnsafeImportUrlError,
)
from app.services.official_import_service import ImportSource


@pytest.fixture
def public_dns(monkeypatch):
    def _fake_getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):
        return [(socket.AF_INET, socket.SOCK_STREAM, 0, "", ("93.184.216.34", 0))]

    monkeypatch.setattr(
        "app.services.http_official_data_importer.socket.getaddrinfo",
        _fake_getaddrinfo,
    )


@pytest.mark.asyncio
async def test_successful_download_returns_import_data(public_dns):
    async def handler(request):
        return httpx.Response(
            200,
            headers={"content-type": "text/csv; charset=utf-8"},
            content=b"province,value\nLusaka,100\n",
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    config = HttpOfficialImportConfig(
        source=ImportSource.ZAMSTATS,
        url="https://example.com/data.csv",
        original_filename=None,
        source_reference="https://example.com/source",
        timeout_seconds=2.0,
        maximum_response_bytes=1024,
        allowed_content_types={"text/csv"},
        headers={"User-Agent": "statflow-test"},
    )

    importer = HttpOfficialDataImporter(config=config, client=client)
    result = await importer.import_data()

    assert result.source == ImportSource.ZAMSTATS
    assert result.original_filename == "data.csv"
    assert result.content == b"province,value\nLusaka,100\n"
    assert result.source_reference == "https://example.com/source"


@pytest.mark.asyncio
async def test_unsupported_scheme_rejected(public_dns):
    config = HttpOfficialImportConfig(
        source=ImportSource.OTHER,
        url="ftp://example.com/data.csv",
        timeout_seconds=2.0,
        maximum_response_bytes=1024,
    )

    importer = HttpOfficialDataImporter(config=config)

    with pytest.raises(UnsafeImportUrlError):
        await importer.import_data()


@pytest.mark.asyncio
async def test_embedded_credentials_rejected(public_dns):
    config = HttpOfficialImportConfig(
        source=ImportSource.OTHER,
        url="https://user:pass@example.com/data.csv",
        timeout_seconds=2.0,
        maximum_response_bytes=1024,
    )

    importer = HttpOfficialDataImporter(config=config)

    with pytest.raises(UnsafeImportUrlError):
        await importer.import_data()


@pytest.mark.asyncio
async def test_localhost_rejected(public_dns):
    config = HttpOfficialImportConfig(
        source=ImportSource.OTHER,
        url="https://localhost/data.csv",
        timeout_seconds=2.0,
        maximum_response_bytes=1024,
    )

    importer = HttpOfficialDataImporter(config=config)

    with pytest.raises(UnsafeImportUrlError):
        await importer.import_data()


@pytest.mark.asyncio
async def test_private_address_rejected(monkeypatch):
    def _fake_getaddrinfo(host, port, family=0, type=0, proto=0, flags=0):
        return [(socket.AF_INET, socket.SOCK_STREAM, 0, "", ("10.0.0.5", 0))]

    monkeypatch.setattr(
        "app.services.http_official_data_importer.socket.getaddrinfo",
        _fake_getaddrinfo,
    )

    config = HttpOfficialImportConfig(
        source=ImportSource.OTHER,
        url="https://example.com/data.csv",
        timeout_seconds=2.0,
        maximum_response_bytes=1024,
    )

    importer = HttpOfficialDataImporter(config=config)

    with pytest.raises(UnsafeImportUrlError):
        await importer.import_data()


@pytest.mark.asyncio
async def test_redirect_limit_enforced(public_dns):
    async def handler(request):
        return httpx.Response(302, headers={"location": "/next"})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    config = HttpOfficialImportConfig(
        source=ImportSource.OTHER,
        url="https://example.com/start.csv",
        timeout_seconds=2.0,
        maximum_response_bytes=1024,
    )

    importer = HttpOfficialDataImporter(config=config, client=client)

    with pytest.raises(UnsafeImportUrlError):
        await importer.import_data()


@pytest.mark.asyncio
async def test_non_success_status_mapped_correctly(public_dns):
    async def handler(request):
        return httpx.Response(404, text="missing")

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    config = HttpOfficialImportConfig(
        source=ImportSource.OTHER,
        url="https://example.com/missing.csv",
        timeout_seconds=2.0,
        maximum_response_bytes=1024,
    )

    importer = HttpOfficialDataImporter(config=config, client=client)

    with pytest.raises(HttpImportStatusError):
        await importer.import_data()


@pytest.mark.asyncio
async def test_empty_body_rejected(public_dns):
    async def handler(request):
        return httpx.Response(200, content=b"")

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    config = HttpOfficialImportConfig(
        source=ImportSource.OTHER,
        url="https://example.com/empty.csv",
        timeout_seconds=2.0,
        maximum_response_bytes=1024,
    )

    importer = HttpOfficialDataImporter(config=config, client=client)

    with pytest.raises(EmptyHttpImportResponseError):
        await importer.import_data()


@pytest.mark.asyncio
async def test_disallowed_content_type_rejected(public_dns):
    async def handler(request):
        return httpx.Response(
            200,
            headers={"content-type": "text/plain"},
            content=b"hello",
        )

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    config = HttpOfficialImportConfig(
        source=ImportSource.OTHER,
        url="https://example.com/data.csv",
        timeout_seconds=2.0,
        maximum_response_bytes=1024,
        allowed_content_types={"application/json"},
    )

    importer = HttpOfficialDataImporter(config=config, client=client)

    with pytest.raises(HttpImportContentTypeError):
        await importer.import_data()


@pytest.mark.asyncio
async def test_oversized_content_length_rejected_before_body_read(public_dns):
    async def handler(request):
        return httpx.Response(200, headers={"content-length": "999999"}, content=b"too-large")

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    config = HttpOfficialImportConfig(
        source=ImportSource.OTHER,
        url="https://example.com/data.csv",
        timeout_seconds=2.0,
        maximum_response_bytes=32,
    )

    importer = HttpOfficialDataImporter(config=config, client=client)

    with pytest.raises(HttpImportResponseTooLargeError):
        await importer.import_data()


@pytest.mark.asyncio
async def test_timeout_mapped_to_typed_exception(public_dns):
    async def handler(request):
        raise httpx.TimeoutException("timed out")

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    config = HttpOfficialImportConfig(
        source=ImportSource.OTHER,
        url="https://example.com/data.csv",
        timeout_seconds=2.0,
        maximum_response_bytes=1024,
    )

    importer = HttpOfficialDataImporter(config=config, client=client)

    with pytest.raises(HttpImportTimeoutError) as excinfo:
        await importer.import_data()

    assert excinfo.value.__cause__ is not None


@pytest.mark.asyncio
async def test_injected_client_is_not_closed(public_dns):
    async def handler(request):
        return httpx.Response(200, content=b"ok")

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    config = HttpOfficialImportConfig(
        source=ImportSource.OTHER,
        url="https://example.com/data.csv",
        timeout_seconds=2.0,
        maximum_response_bytes=1024,
    )

    importer = HttpOfficialDataImporter(config=config, client=client)
    await importer.import_data()

    assert not client.is_closed


@pytest.mark.asyncio
async def test_importer_owned_client_is_closed(monkeypatch, public_dns):
    class FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            self.closed = False

        async def get(self, url, *args, **kwargs):
            return httpx.Response(200, content=b"ok")

        async def aclose(self):
            self.closed = True

    monkeypatch.setattr(
        "app.services.http_official_data_importer.httpx.AsyncClient",
        FakeAsyncClient,
    )

    config = HttpOfficialImportConfig(
        source=ImportSource.OTHER,
        url="https://example.com/data.csv",
        timeout_seconds=2.0,
        maximum_response_bytes=1024,
    )

    importer = HttpOfficialDataImporter(config=config)
    await importer.import_data()

    assert importer._client.closed is True


@pytest.mark.asyncio
async def test_no_retries_occur_by_default(public_dns):
    attempts = []

    async def handler(request):
        attempts.append(request.url)
        return httpx.Response(200, content=b"ok")

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    config = HttpOfficialImportConfig(
        source=ImportSource.OTHER,
        url="https://example.com/data.csv",
        timeout_seconds=2.0,
        maximum_response_bytes=1024,
    )

    importer = HttpOfficialDataImporter(config=config, client=client)
    await importer.import_data()

    assert len(attempts) == 1
