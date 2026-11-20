import pytest

from capture.browser import capture_page
from support.recording import DOWNLOAD, replay_page

pytestmark = pytest.mark.integration


async def test_replay_returns_successful_response(local_site, tmp_path) -> None:
    capture = await capture_page(f"{local_site.base_url}/start", tmp_path)
    local_site.stop()
    replay = await replay_page(tmp_path, tmp_path / "replay", capture.final_url)

    assert replay.status_code == 200


async def test_replay_executes_page_javascript(local_site, tmp_path) -> None:
    capture = await capture_page(f"{local_site.base_url}/start", tmp_path)
    local_site.stop()
    replay = await replay_page(tmp_path, tmp_path / "replay", capture.final_url)

    assert replay.page_state == "rendered"


async def test_replay_serves_downloaded_resource(local_site, tmp_path) -> None:
    capture = await capture_page(f"{local_site.base_url}/start", tmp_path)
    local_site.stop()
    replay = await replay_page(tmp_path, tmp_path / "replay", capture.final_url)

    assert replay.download_content == DOWNLOAD


async def test_replay_loads_page_image(local_site, tmp_path) -> None:
    capture = await capture_page(f"{local_site.base_url}/start", tmp_path)
    local_site.stop()
    replay = await replay_page(tmp_path, tmp_path / "replay", capture.final_url)

    assert replay.image_width == 1
