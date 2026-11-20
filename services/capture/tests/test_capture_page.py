from pathlib import Path

import pytest

from capture.browser import (
    CaptureLimitExceeded,
    capture_page,
    extract_links,
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


def test_extract_links_rejects_excessive_discovery() -> None:
    html = '<a href="/one">One</a><a href="/two">Two</a>'

    with pytest.raises(CaptureLimitExceeded, match="discovered-link limit"):
        extract_links(html, "https://example.org/", max_links=1)
