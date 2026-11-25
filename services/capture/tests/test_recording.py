import asyncio
import gzip
from pathlib import Path

import pytest
from support.recording import DOWNLOAD, LocalSite

from capture.browser import (
    CaptureFailureCode,
    CaptureLimits,
    CaptureNavigationFailed,
    capture_local_page,
    capture_page,
)
from capture.browser.recording import PyWBRecorder
from utils.io import read_gzip_files


@pytest.mark.integration
async def test_capture_follows_redirect(local_site: LocalSite, tmp_path: Path) -> None:
    capture = await capture_local_page(f"{local_site.base_url}/start", tmp_path)
    local_site.stop()

    assert capture.final_url.endswith("/page")
    assert capture.redirect_chain == (
        f"{local_site.base_url}/start",
        f"{local_site.base_url}/redirected",
        f"{local_site.base_url}/page",
    )


@pytest.mark.integration
async def test_capture_fails_when_navigation_response_is_interrupted(
    local_site: LocalSite,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("capture.browser.page.DOWNLOAD_EVENT_TIMEOUT_SECONDS", 0.05)

    with pytest.raises(CaptureNavigationFailed) as error:
        await capture_page(
            f"{local_site.base_url}/slow",
            tmp_path,
            limits=CaptureLimits(
                navigation_timeout_milliseconds=100,
                allow_private_networks=True,
            ),
        )

    assert error.value.reason_code == CaptureFailureCode.NAVIGATION_FAILED


@pytest.mark.integration
async def test_cancellation_stops_capture_recorder(
    local_site: LocalSite,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    recorder_started = asyncio.Event()
    stopped_process_codes: list[int | None] = []

    original_start = PyWBRecorder.start
    original_stop = PyWBRecorder.stop

    async def start_recorder(recorder: PyWBRecorder) -> PyWBRecorder:
        result = await original_start(recorder)
        recorder_started.set()

        return result

    async def stop_recorder(recorder: PyWBRecorder) -> None:
        await original_stop(recorder)

        if recorder.process is not None:
            stopped_process_codes.append(recorder.process.returncode)

    monkeypatch.setattr(PyWBRecorder, "start", start_recorder)
    monkeypatch.setattr(PyWBRecorder, "stop", stop_recorder)

    capture = asyncio.create_task(capture_local_page(f"{local_site.base_url}/page", tmp_path))

    await recorder_started.wait()
    capture.cancel()

    with pytest.raises(asyncio.CancelledError):
        await capture

    assert stopped_process_codes
    assert all(code is not None for code in stopped_process_codes)


@pytest.mark.integration
async def test_capture_warc_segments_are_valid_gzip_records(
    local_site: LocalSite,
    tmp_path: Path,
) -> None:
    capture = await capture_local_page(f"{local_site.base_url}/start", tmp_path)
    local_site.stop()

    assert capture.warc_files

    for warc_file in capture.warc_files:
        content = gzip.decompress(warc_file.read_bytes())

        assert content.startswith(b"WARC/1.")
        assert b"WARC-Type: request" in content or b"WARC-Type: response" in content


@pytest.mark.integration
async def test_capture_preserves_http_error_response(
    local_site: LocalSite,
    tmp_path: Path,
) -> None:
    capture = await capture_local_page(f"{local_site.base_url}/missing", tmp_path)
    local_site.stop()

    assert capture.status_code == 404
    assert capture.warc_files


@pytest.mark.integration
async def test_capture_returns_successful_response(local_site: LocalSite, tmp_path: Path) -> None:
    capture = await capture_local_page(f"{local_site.base_url}/start", tmp_path)
    local_site.stop()

    assert capture.status_code == 200


@pytest.mark.integration
async def test_capture_extracts_page_title(local_site: LocalSite, tmp_path: Path) -> None:
    capture = await capture_local_page(f"{local_site.base_url}/start", tmp_path)
    local_site.stop()

    assert capture.title == "Recorder acceptance page"


@pytest.mark.integration
async def test_capture_discovers_page_links(local_site: LocalSite, tmp_path: Path) -> None:
    capture = await capture_local_page(f"{local_site.base_url}/start", tmp_path)
    local_site.stop()

    assert any(url.endswith("/next") for url in capture.discovered_urls)


@pytest.mark.integration
async def test_capture_produces_warc_artifacts(local_site: LocalSite, tmp_path: Path) -> None:
    capture = await capture_local_page(f"{local_site.base_url}/start", tmp_path)
    local_site.stop()

    assert capture.warc_files


@pytest.mark.integration
async def test_capture_records_request_record(local_site: LocalSite, tmp_path: Path) -> None:
    capture = await capture_local_page(f"{local_site.base_url}/start", tmp_path)
    local_site.stop()

    warc_content = read_gzip_files(capture.warc_files)

    assert b"WARC-Type: request" in warc_content


@pytest.mark.integration
async def test_capture_records_response_record(local_site: LocalSite, tmp_path: Path) -> None:
    capture = await capture_local_page(f"{local_site.base_url}/start", tmp_path)
    local_site.stop()

    warc_content = read_gzip_files(capture.warc_files)

    assert b"WARC-Type: response" in warc_content


@pytest.mark.integration
async def test_capture_records_html_document(local_site: LocalSite, tmp_path: Path) -> None:
    capture = await capture_local_page(f"{local_site.base_url}/start", tmp_path)
    local_site.stop()

    warc_content = read_gzip_files(capture.warc_files)

    assert b"Recorder acceptance page" in warc_content


@pytest.mark.integration
async def test_capture_records_stylesheet(local_site: LocalSite, tmp_path: Path) -> None:
    capture = await capture_local_page(f"{local_site.base_url}/start", tmp_path)
    local_site.stop()

    warc_content = read_gzip_files(capture.warc_files)

    assert b"site.css" in warc_content


@pytest.mark.integration
async def test_capture_records_script(local_site: LocalSite, tmp_path: Path) -> None:
    capture = await capture_local_page(f"{local_site.base_url}/start", tmp_path)
    local_site.stop()

    warc_content = read_gzip_files(capture.warc_files)

    assert b"app.js" in warc_content


@pytest.mark.integration
async def test_capture_records_image(local_site: LocalSite, tmp_path: Path) -> None:
    capture = await capture_local_page(f"{local_site.base_url}/start", tmp_path)
    local_site.stop()

    warc_content = read_gzip_files(capture.warc_files)

    assert b"pixel.svg" in warc_content


@pytest.mark.integration
async def test_capture_records_download(local_site: LocalSite, tmp_path: Path) -> None:
    capture = await capture_local_page(f"{local_site.base_url}/start", tmp_path)
    local_site.stop()

    warc_content = read_gzip_files(capture.warc_files)

    assert DOWNLOAD.encode() in warc_content


@pytest.mark.integration
async def test_capture_records_redirected_download(
    local_site: LocalSite,
    tmp_path: Path,
) -> None:
    capture = await capture_local_page(f"{local_site.base_url}/redirect-to-download", tmp_path)
    local_site.stop()

    assert capture.final_url.endswith("/assets/download.bin")
    assert capture.status_code == 200
    assert capture.content_type == "application/octet-stream"
    assert capture.redirect_chain == (
        f"{local_site.base_url}/redirect-to-download",
        f"{local_site.base_url}/assets/download.bin",
    )

    warc_content = read_gzip_files(capture.warc_files)

    assert DOWNLOAD.encode() in warc_content


@pytest.mark.integration
async def test_capture_records_direct_download(local_site: LocalSite, tmp_path: Path) -> None:
    capture = await capture_local_page(f"{local_site.base_url}/assets/download.bin", tmp_path)
    local_site.stop()

    assert capture.final_url.endswith("/assets/download.bin")
    assert capture.warc_files

    warc_content = read_gzip_files(capture.warc_files)

    assert DOWNLOAD.encode() in warc_content


@pytest.mark.integration
async def test_capture_records_redirected_pdf(
    local_site: LocalSite,
    tmp_path: Path,
) -> None:
    capture = await capture_local_page(f"{local_site.base_url}/redirect-to-pdf", tmp_path)
    local_site.stop()

    assert capture.final_url.endswith("/assets/document.pdf")
    assert capture.status_code == 200
    assert capture.content_type == "application/pdf"
    assert capture.redirect_chain == (
        f"{local_site.base_url}/redirect-to-pdf",
        f"{local_site.base_url}/assets/document.pdf",
    )

    warc_content = read_gzip_files(capture.warc_files)

    assert b"%PDF-1.4" in warc_content


@pytest.mark.integration
async def test_capture_records_direct_pdf(local_site: LocalSite, tmp_path: Path) -> None:
    capture = await capture_local_page(f"{local_site.base_url}/assets/document.pdf", tmp_path)
    local_site.stop()

    assert capture.content_type == "application/pdf"
    assert capture.title == ""
    assert capture.discovered_urls == ()

    warc_content = read_gzip_files(capture.warc_files)

    assert b"%PDF-1.4" in warc_content
