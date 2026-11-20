from pathlib import Path

import pytest

from capture.browser import PageCapture
from support.recording import DOWNLOAD

pytestmark = pytest.mark.integration


async def test_capture_follows_redirect(captured_page: tuple[PageCapture, Path]) -> None:
    capture, _ = captured_page

    assert capture.final_url.endswith("/page")


async def test_capture_returns_successful_response(captured_page: tuple[PageCapture, Path]) -> None:
    capture, _ = captured_page

    assert capture.status_code == 200


async def test_capture_extracts_page_title(captured_page: tuple[PageCapture, Path]) -> None:
    capture, _ = captured_page

    assert capture.title == "Recorder acceptance page"


async def test_capture_discovers_page_links(captured_page: tuple[PageCapture, Path]) -> None:
    capture, _ = captured_page

    assert any(url.endswith("/next") for url in capture.discovered_urls)


def test_capture_records_request_and_response_records(warc_content: bytes) -> None:
    assert b"WARC-Type: request" in warc_content and b"WARC-Type: response" in warc_content


def test_capture_records_redirect_response(warc_content: bytes) -> None:
    assert b"HTTP/1.1 302" in warc_content


def test_capture_records_html_document(warc_content: bytes) -> None:
    assert b"Recorder acceptance page" in warc_content


def test_capture_records_stylesheet(warc_content: bytes) -> None:
    assert b"site.css" in warc_content


def test_capture_records_script(warc_content: bytes) -> None:
    assert b"app.js" in warc_content


def test_capture_records_image(warc_content: bytes) -> None:
    assert b"pixel.svg" in warc_content


def test_capture_records_download(warc_content: bytes) -> None:
    assert DOWNLOAD.encode() in warc_content
