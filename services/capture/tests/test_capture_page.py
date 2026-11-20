from pathlib import Path

import pytest

from capture.browser import (
    CaptureLimitExceeded,
    CaptureLimits,
    capture_page,
    extract_links,
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


def test_capture_limits_have_bounded_defaults() -> None:
    limits = CaptureLimits()

    assert limits.max_requests > 0
    assert limits.max_document_bytes > 0
    assert limits.max_discovered_links > 0
    assert limits.allow_private_networks is False
