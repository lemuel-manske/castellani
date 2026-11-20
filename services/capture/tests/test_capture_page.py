from pathlib import Path

import pytest

from capture.browser import capture_page


@pytest.mark.asyncio
async def test_capture_rejects_non_http_urls(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="absolute HTTP or HTTPS URL"):
        await capture_page("file:///etc/passwd", tmp_path)
