import pytest

from utils.web import is_html_content_type, is_pdf_content_type, is_safe_request_url, is_valid_url


def test_html_content_type_accepts_html_media_types() -> None:
    assert is_html_content_type("text/html; charset=utf-8")
    assert is_html_content_type("application/xhtml+xml")


def test_html_content_type_rejects_binary_media_types() -> None:
    assert not is_html_content_type("application/pdf")
    assert not is_html_content_type("application/octet-stream")


def test_html_content_type_defaults_to_html_when_missing() -> None:
    assert is_html_content_type(None)


def test_pdf_content_type_accepts_pdf_media_type() -> None:
    assert is_pdf_content_type("application/pdf; charset=binary")
    assert not is_pdf_content_type("application/octet-stream")


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
