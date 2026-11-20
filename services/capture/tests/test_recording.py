import pytest

from capture.browser import capture_page
from support.recording import DOWNLOAD, read_warc_files

pytestmark = pytest.mark.integration


async def test_capture_follows_redirect(local_site, tmp_path) -> None:
    capture = await capture_page(f"{local_site.base_url}/start", tmp_path)
    local_site.stop()

    assert capture.final_url.endswith("/page")


async def test_capture_returns_successful_response(local_site, tmp_path) -> None:
    capture = await capture_page(f"{local_site.base_url}/start", tmp_path)
    local_site.stop()

    assert capture.status_code == 200


async def test_capture_extracts_page_title(local_site, tmp_path) -> None:
    capture = await capture_page(f"{local_site.base_url}/start", tmp_path)
    local_site.stop()

    assert capture.title == "Recorder acceptance page"


async def test_capture_discovers_page_links(local_site, tmp_path) -> None:
    capture = await capture_page(f"{local_site.base_url}/start", tmp_path)
    local_site.stop()

    assert any(url.endswith("/next") for url in capture.discovered_urls)


async def test_capture_produces_warc_artifacts(local_site, tmp_path) -> None:
    capture = await capture_page(f"{local_site.base_url}/start", tmp_path)
    local_site.stop()

    assert capture.warc_files


async def test_capture_records_request_record(local_site, tmp_path) -> None:
    capture = await capture_page(f"{local_site.base_url}/start", tmp_path)
    local_site.stop()

    warc_content = read_warc_files(capture.warc_files)

    assert b"WARC-Type: request" in warc_content


async def test_capture_records_response_record(local_site, tmp_path) -> None:
    capture = await capture_page(f"{local_site.base_url}/start", tmp_path)
    local_site.stop()

    warc_content = read_warc_files(capture.warc_files)

    assert b"WARC-Type: response" in warc_content


async def test_capture_records_redirect_response(local_site, tmp_path) -> None:
    capture = await capture_page(f"{local_site.base_url}/start", tmp_path)
    local_site.stop()

    warc_content = read_warc_files(capture.warc_files)

    assert b"HTTP/1.1 302" in warc_content


async def test_capture_records_html_document(local_site, tmp_path) -> None:
    capture = await capture_page(f"{local_site.base_url}/start", tmp_path)
    local_site.stop()

    warc_content = read_warc_files(capture.warc_files)

    assert b"Recorder acceptance page" in warc_content


async def test_capture_records_stylesheet(local_site, tmp_path) -> None:
    capture = await capture_page(f"{local_site.base_url}/start", tmp_path)
    local_site.stop()

    warc_content = read_warc_files(capture.warc_files)

    assert b"site.css" in warc_content


async def test_capture_records_script(local_site, tmp_path) -> None:
    capture = await capture_page(f"{local_site.base_url}/start", tmp_path)
    local_site.stop()

    warc_content = read_warc_files(capture.warc_files)

    assert b"app.js" in warc_content


async def test_capture_records_image(local_site, tmp_path) -> None:
    capture = await capture_page(f"{local_site.base_url}/start", tmp_path)
    local_site.stop()

    warc_content = read_warc_files(capture.warc_files)

    assert b"pixel.svg" in warc_content


async def test_capture_records_download(local_site, tmp_path) -> None:
    capture = await capture_page(f"{local_site.base_url}/start", tmp_path)
    local_site.stop()

    warc_content = read_warc_files(capture.warc_files)

    assert DOWNLOAD.encode() in warc_content
