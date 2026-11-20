import asyncio
from pathlib import Path

import pytest

from capture.browser import capture_page
from support.recording import DOWNLOAD, LocalSite, replay_page

pytestmark = pytest.mark.integration


async def test_replay_returns_successful_response(
    local_site: LocalSite,
    tmp_path: Path,
) -> None:
    capture = await capture_page(f"{local_site.base_url}/start", tmp_path)
    local_site.stop()

    replay = await replay_page(tmp_path, tmp_path / "replay", capture.final_url)

    assert replay.status_code == 200


async def test_replay_executes_page_javascript(
    local_site: LocalSite,
    tmp_path: Path,
) -> None:
    capture = await capture_page(f"{local_site.base_url}/start", tmp_path)
    local_site.stop()

    replay = await replay_page(tmp_path, tmp_path / "replay", capture.final_url)

    assert replay.page_state == "rendered"


async def test_replay_serves_downloaded_resource(
    local_site: LocalSite,
    tmp_path: Path,
) -> None:
    capture = await capture_page(f"{local_site.base_url}/start", tmp_path)
    local_site.stop()

    replay = await replay_page(tmp_path, tmp_path / "replay", capture.final_url)

    assert replay.download_content == DOWNLOAD


async def test_replay_loads_page_image(
    local_site: LocalSite,
    tmp_path: Path,
) -> None:
    capture = await capture_page(f"{local_site.base_url}/start", tmp_path)
    local_site.stop()

    replay = await replay_page(tmp_path, tmp_path / "replay", capture.final_url)

    assert replay.image_width == 1


async def test_concurrent_captures_replay_only_their_own_pages(
    local_site: LocalSite,
    tmp_path: Path,
) -> None:
    first_capture, second_capture = await asyncio.gather(
        capture_page(f"{local_site.base_url}/capture/first", tmp_path / "first"),
        capture_page(f"{local_site.base_url}/capture/second", tmp_path / "second"),
    )
    local_site.stop()

    first_replay = await replay_page(
        tmp_path / "first",
        tmp_path / "first-replay",
        first_capture.final_url,
    )
    second_replay = await replay_page(
        tmp_path / "second",
        tmp_path / "second-replay",
        second_capture.final_url,
    )

    assert (first_replay.page_title, second_replay.page_title) == (
        "First capture",
        "Second capture",
    )
