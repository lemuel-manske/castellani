from pathlib import Path

import pytest

from capture.browser import (
    CaptureFailureCode,
    CaptureLimitExceeded,
    InvalidCaptureURL,
    capture_page,
    extract_links,
)


@pytest.mark.asyncio
async def test_capture_rejects_non_http_urls(tmp_path: Path) -> None:
    with pytest.raises(
        InvalidCaptureURL,
        match="capture URL must be an absolute HTTP or HTTPS URL without credentials",
    ) as error:
        await capture_page("file:///etc/passwd", tmp_path)

    assert error.value.reason_code == CaptureFailureCode.INVALID_URL


@pytest.mark.asyncio
async def test_capture_rejects_malformed_http_urls(tmp_path: Path) -> None:
    with pytest.raises(
        InvalidCaptureURL,
        match="capture URL must be an absolute HTTP or HTTPS URL without credentials",
    ) as error:
        await capture_page("http://[", tmp_path)

    assert error.value.reason_code == CaptureFailureCode.INVALID_URL


def test_extract_links_rejects_excessive_discovery() -> None:
    html = '<a href="/one">One</a><a href="/two">Two</a>'

    with pytest.raises(CaptureLimitExceeded, match="discovered-link limit") as error:
        extract_links(html, "https://example.org/", max_links=1)

    assert error.value.reason_code == CaptureFailureCode.DISCOVERED_LINK_LIMIT_EXCEEDED
