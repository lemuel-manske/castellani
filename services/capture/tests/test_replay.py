import pytest

from support.recording import DOWNLOAD, ReplayResult

pytestmark = pytest.mark.integration


async def test_replay_returns_successful_response(replayed_page: ReplayResult) -> None:
    assert replayed_page.status_code == 200


async def test_replay_executes_page_javascript(replayed_page: ReplayResult) -> None:
    assert replayed_page.page_state == "rendered"


async def test_replay_serves_downloaded_resource(replayed_page: ReplayResult) -> None:
    assert replayed_page.download_content == DOWNLOAD


async def test_replay_loads_page_image(replayed_page: ReplayResult) -> None:
    assert replayed_page.image_width == 1
