from pathlib import Path

import pytest

from capture.browser import (
    CaptureLimitExceeded,
    capture_page,
    extract_links,
    is_html_content_type,
    is_safe_request_url,
    is_valid_url,
)


@pytest.mark.asyncio
async def test_capture_rejects_non_http_urls(tmp_path: Path) -> None:
    with pytest.raises(
        ValueError,
        match="capture URL must be an absolute HTTP or HTTPS URL without credentials",
    ):
        await capture_page("file:///etc/passwd", tmp_path)


@pytest.mark.asyncio
async def test_capture_rejects_malformed_http_urls(tmp_path: Path) -> None:
    with pytest.raises(
        ValueError,
        match="capture URL must be an absolute HTTP or HTTPS URL without credentials",
    ):
        await capture_page("http://[", tmp_path)


def test_url_validation_rejects_embedded_credentials() -> None:
    assert not is_valid_url("https://user:password@example.org/private")


def test_url_validation_rejects_invalid_ports() -> None:
    assert not is_valid_url("https://example.org:invalid")


@pytest.mark.asyncio
async def test_request_validation_rejects_loopback_addresses() -> None:
    assert not await is_safe_request_url("http://127.0.0.1:8080/")


@pytest.mark.asyncio
async def test_request_validation_rejects_link_local_addresses() -> None:
    assert not await is_safe_request_url("http://169.254.169.254/latest/meta-data/")


@pytest.mark.asyncio
async def test_request_validation_allows_private_addresses_only_when_explicitly_enabled() -> None:
    assert await is_safe_request_url(
        "http://127.0.0.1:8080/",
        allow_private_networks=True,
    )


def test_extract_links_rejects_excessive_discovery() -> None:
    html = '<a href="/one">One</a><a href="/two">Two</a>'

    with pytest.raises(CaptureLimitExceeded, match="discovered-link limit"):
        extract_links(html, "https://example.org/", max_links=1)


def test_html_content_type_accepts_html_media_types() -> None:
    assert is_html_content_type("text/html; charset=utf-8")
    assert is_html_content_type("application/xhtml+xml")


def test_html_content_type_rejects_binary_media_types() -> None:
    assert not is_html_content_type("application/pdf")
    assert not is_html_content_type("application/octet-stream")


def test_html_content_type_defaults_to_html_when_missing() -> None:
    assert is_html_content_type(None)



def test_pdf_content_type_accepts_pdf_media_type() -> None:
    from capture.browser import is_pdf_content_type

    assert is_pdf_content_type("application/pdf; charset=binary")
    assert not is_pdf_content_type("application/octet-stream")
