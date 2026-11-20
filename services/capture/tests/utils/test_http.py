import pytest

from utils.http import is_safe_request_url, is_valid_url


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
