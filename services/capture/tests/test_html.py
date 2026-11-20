from pathlib import Path

import pytest

from capture.browser import capture_page, extract_links


def test_extract_links_resolves_relative_urls_and_preserves_first_occurrence() -> None:
    html = """
    <html>
      <body>
        <a href="/about">About</a>
        <a href="https://example.org/archive">Archive</a>
        <a href="/about">About again</a>
        <a href="mailto:contact@example.org">Email</a>
        <a href="javascript:void(0)">Script</a>
        <a href="">Empty</a>
      </body>
    </html>
    """

    links = extract_links(html, "https://example.org/start")

    assert links == (
        "https://example.org/about",
        "https://example.org/archive",
    )


@pytest.mark.asyncio
async def test_capture_rejects_non_http_urls(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="absolute HTTP or HTTPS URL"):
        await capture_page("file:///etc/passwd", tmp_path)
