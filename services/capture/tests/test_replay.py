import asyncio
from pathlib import Path

import httpx
import pytest
from support.recording import DOWNLOAD, PDF, LocalSite, replay_page

from capture.browser import capture_local_page
from capture.browser.recording import PyWBReplayServer
from utils.io import read_gzip_files

pytestmark = pytest.mark.integration


async def test_replay_returns_successful_response(
    local_site: LocalSite,
    tmp_path: Path,
) -> None:
    capture = await capture_local_page(f"{local_site.base_url}/start", tmp_path)
    local_site.stop()

    replay = await replay_page(tmp_path, tmp_path / "replay", capture.final_url)

    assert replay.status_code == 200


async def test_replay_executes_page_javascript(
    local_site: LocalSite,
    tmp_path: Path,
) -> None:
    capture = await capture_local_page(f"{local_site.base_url}/start", tmp_path)
    local_site.stop()

    replay = await replay_page(tmp_path, tmp_path / "replay", capture.final_url)

    assert replay.page_state == "rendered"


async def test_replay_serves_downloaded_resource(
    local_site: LocalSite,
    tmp_path: Path,
) -> None:
    capture = await capture_local_page(f"{local_site.base_url}/start", tmp_path)
    local_site.stop()

    replay = await replay_page(tmp_path, tmp_path / "replay", capture.final_url)

    assert replay.download_content == DOWNLOAD


async def test_replay_applies_recorded_stylesheet(
    local_site: LocalSite,
    tmp_path: Path,
) -> None:
    capture = await capture_local_page(f"{local_site.base_url}/start", tmp_path)
    local_site.stop()

    replay = await replay_page(tmp_path, tmp_path / "replay", capture.final_url)

    assert "sans-serif" in replay.body_font_family


async def test_replay_loads_page_image(
    local_site: LocalSite,
    tmp_path: Path,
) -> None:
    capture = await capture_local_page(f"{local_site.base_url}/start", tmp_path)
    local_site.stop()

    replay = await replay_page(tmp_path, tmp_path / "replay", capture.final_url)

    assert replay.image_width == 1


async def test_concurrent_captures_replay_only_their_own_pages(
    local_site: LocalSite,
    tmp_path: Path,
) -> None:
    first_capture, second_capture = await asyncio.gather(
        capture_local_page(f"{local_site.base_url}/capture/first", tmp_path / "first"),
        capture_local_page(f"{local_site.base_url}/capture/second", tmp_path / "second"),
    )
    local_site.stop()

    first_warc = read_gzip_files(first_capture.warc_files)
    second_warc = read_gzip_files(second_capture.warc_files)

    assert b"First capture" in first_warc
    assert b"Second capture" not in first_warc
    assert b"Second capture" in second_warc
    assert b"First capture" not in second_warc

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


async def test_replay_serves_direct_download(
    local_site: LocalSite,
    tmp_path: Path,
) -> None:
    capture = await capture_local_page(f"{local_site.base_url}/assets/download.bin", tmp_path)
    local_site.stop()

    replayer = PyWBReplayServer(tmp_path, tmp_path / "replay")

    replay_server = await replayer.start()

    try:
        async with httpx.AsyncClient(trust_env=False) as client:
            response = await client.get(replay_server.replay_url(capture.final_url))

        assert response.status_code == 200
        assert response.content == DOWNLOAD.encode()
    finally:
        await replay_server.stop()


async def test_replay_serves_direct_pdf(
    local_site: LocalSite,
    tmp_path: Path,
) -> None:
    capture = await capture_local_page(f"{local_site.base_url}/assets/document.pdf", tmp_path)
    local_site.stop()

    replayer = PyWBReplayServer(tmp_path, tmp_path / "replay")

    replay_server = await replayer.start()

    try:
        async with httpx.AsyncClient(trust_env=False) as client:
            response = await client.get(replay_server.replay_url(capture.final_url))

        assert response.status_code == 200
        assert response.content == PDF
        assert response.headers["content-type"].startswith("application/pdf")
    finally:
        await replay_server.stop()
