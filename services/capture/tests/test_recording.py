import asyncio
import gzip
import json
import signal
import socket
import subprocess
import threading
from collections.abc import Iterator
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import httpx
from playwright.async_api import async_playwright
import pytest

from capture.browser import capture_page

HOST = "127.0.0.1"
COLLECTION_NAME = "capture"
REPLAY_STARTUP_TIMEOUT_SECONDS = 15

PAGE = """<!doctype html>
<html>
  <head>
    <title>Recorder acceptance page</title>
    <link rel="stylesheet" href="/assets/site.css">
    <script defer src="/assets/app.js"></script>
  </head>
  <body>
    <h1>Recorder acceptance page</h1>
    <p id="state">waiting</p>
    <p id="download">waiting</p>
    <img src="/assets/pixel.svg" alt="pixel">
    <a href="/next">Next</a>
  </body>
</html>
"""

STYLESHEET = "body { font-family: sans-serif; }"
SCRIPT = """
document.querySelector("#state").textContent = "rendered";

fetch("/assets/download.bin")
  .then((response) => response.text())
  .then((body) => {
    document.querySelector("#download").textContent = body;
  });
"""
IMAGE = """<svg xmlns="http://www.w3.org/2000/svg" width="1" height="1">
  <rect width="1" height="1" fill="#000"/>
</svg>"""
DOWNLOAD = "archive-download-payload"


def available_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind((HOST, 0))

        return int(listener.getsockname()[1])


@dataclass
class LocalSite:
    server: ThreadingHTTPServer
    thread: threading.Thread
    base_url: str
    stopped: bool = False

    def stop(self) -> None:
        if self.stopped:
            return

        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.stopped = True


@pytest.fixture
def local_site() -> Iterator[LocalSite]:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            path = self.path.split("?", maxsplit=1)[0]

            if path == "/start":
                self.send_response(302)
                self.send_header("Location", "/page")
                self.end_headers()

                return

            if path == "/page":
                self._write(PAGE.encode(), "text/html; charset=utf-8")

                return

            if path == "/assets/site.css":
                self._write(STYLESHEET.encode(), "text/css")

                return

            if path == "/assets/app.js":
                self._write(SCRIPT.encode(), "text/javascript")

                return

            if path == "/assets/pixel.svg":
                self._write(IMAGE.encode(), "image/svg+xml")

                return

            if path == "/assets/download.bin":
                self._write(
                    DOWNLOAD.encode(),
                    "application/octet-stream",
                    "attachment; filename=download.bin",
                )

                return

            self.send_error(404)

        def _write(
            self,
            body: bytes,
            content_type: str,
            content_disposition: str | None = None,
        ) -> None:
            self.send_response(200)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))

            if content_disposition:
                self.send_header("Content-Disposition", content_disposition)

            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format: str, *args: object) -> None:
            return

    server = ThreadingHTTPServer((HOST, 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    site = LocalSite(
        server=server,
        thread=thread,
        base_url=f"http://{HOST}:{server.server_port}",
    )

    try:
        yield site
    finally:
        site.stop()


async def wait_for_server(process: asyncio.subprocess.Process, port: int) -> None:
    deadline = asyncio.get_running_loop().time() + REPLAY_STARTUP_TIMEOUT_SECONDS

    async with httpx.AsyncClient(trust_env=False, timeout=1) as client:
        while asyncio.get_running_loop().time() < deadline:
            if process.returncode is not None:
                raise RuntimeError("pywb replay server exited before becoming ready")

            try:
                await client.get(f"http://{HOST}:{port}/")

                return
            except httpx.TransportError:
                await asyncio.sleep(0.1)

    raise TimeoutError("pywb replay server did not become ready in time")


async def stop_server(process: asyncio.subprocess.Process) -> None:
    if process.returncode is not None:
        return

    process.send_signal(signal.SIGINT)

    try:
        await asyncio.wait_for(process.wait(), timeout=10)
    except TimeoutError:
        process.kill()
        await process.wait()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_capture_records_and_replays_page_without_origin(
    local_site: LocalSite,
    tmp_path: Path,
) -> None:
    capture_dir = tmp_path / "capture"
    capture = await capture_page(f"{local_site.base_url}/start", capture_dir)

    assert capture.final_url == f"{local_site.base_url}/page"
    assert capture.status_code == 200
    assert capture.title == "Recorder acceptance page"
    assert f"{local_site.base_url}/next" in capture.discovered_urls
    assert capture.warc_files

    warc_content = b""

    for warc_file in capture.warc_files:
        with gzip.open(warc_file, "rb") as archive:
            warc_content += archive.read()

    assert b"WARC-Type: request" in warc_content
    assert b"WARC-Type: response" in warc_content
    assert b"HTTP/1.1 302" in warc_content
    assert b"Recorder acceptance page" in warc_content
    assert b"site.css" in warc_content
    assert b"app.js" in warc_content
    assert b"pixel.svg" in warc_content
    assert DOWNLOAD.encode() in warc_content

    local_site.stop()

    await asyncio.to_thread(
        subprocess.run,
        ["wb-manager", "reindex", COLLECTION_NAME],
        cwd=capture_dir,
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )

    replay_dir = tmp_path / "replay"
    replay_dir.mkdir()
    replay_config = f"""
collections_root: {json.dumps(str(capture_dir / "collections"))}
archive_paths:
  - archive
index_paths:
  - indexes
framed_replay: false
"""
    (replay_dir / "config.yaml").write_text(replay_config, encoding="utf-8")

    replay_port = available_port()
    replay_process = await asyncio.create_subprocess_exec(
        "wayback",
        "-p",
        str(replay_port),
        cwd=replay_dir,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
    )

    try:
        await wait_for_server(replay_process, replay_port)

        replay_url = f"http://{HOST}:{replay_port}/{COLLECTION_NAME}/{capture.final_url}"

        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(headless=True)

            try:
                page = await browser.new_page()
                response = await page.goto(replay_url, wait_until="domcontentloaded")

                assert response is not None
                assert response.status == 200

                await page.wait_for_function(
                    "document.querySelector('#download')?.textContent === "
                    "'archive-download-payload'"
                )

                assert await page.locator("#state").inner_text() == "rendered"
                assert await page.locator("#download").inner_text() == DOWNLOAD
                assert await page.locator("img").evaluate("(image) => image.naturalWidth") == 1
            finally:
                await browser.close()
    finally:
        await stop_server(replay_process)
