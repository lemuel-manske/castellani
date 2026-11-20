from pathlib import Path

import pytest
import pytest_asyncio

from capture.browser import PageCapture, capture_page
from support.recording import (
    LocalSite,
    ReplayResult,
    read_warc_files,
    replay_page,
    start_local_site,
)


@pytest.fixture(scope="module")
def local_site() -> LocalSite:
    site = start_local_site()

    try:
        yield site
    finally:
        site.stop()


@pytest_asyncio.fixture(scope="module")
async def captured_page(
    local_site: LocalSite,
    tmp_path_factory: pytest.TempPathFactory,
) -> tuple[PageCapture, Path]:
    capture_dir = tmp_path_factory.mktemp("capture")
    capture = await capture_page(f"{local_site.base_url}/start", capture_dir)
    local_site.stop()

    return capture, capture_dir


@pytest.fixture(scope="module")
def warc_content(captured_page: tuple[PageCapture, Path]) -> bytes:
    capture, _ = captured_page

    return read_warc_files(capture.warc_files)


@pytest_asyncio.fixture(scope="module")
async def replayed_page(
    captured_page: tuple[PageCapture, Path],
    tmp_path_factory: pytest.TempPathFactory,
) -> ReplayResult:
    capture, capture_dir = captured_page

    return await replay_page(
        capture_dir,
        tmp_path_factory.mktemp("replay"),
        capture.final_url,
    )
