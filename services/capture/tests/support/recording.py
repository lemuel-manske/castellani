import threading
import time
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from playwright.async_api import async_playwright

from capture.recording import PyWBReplayServer

HOST = "127.0.0.1"

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

CAPTURE_PAGES = {
    "/capture/first": "First capture",
    "/capture/second": "Second capture",
}

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

PDF = (
    b"%PDF-1.4\\n"
    b"1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\\n"
    b"2 0 obj<</Type/Pages/Count 0/Kids[]>>endobj\\n"
    b"trailer<</Root 1 0 R>>\\n%%EOF"
)


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


def start_local_site() -> LocalSite:
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            path = self.path.split("?", maxsplit=1)[0]

            if path == "/start":
                self.send_response(302)
                self.send_header("Location", "/redirected")
                self.end_headers()

                return

            if path == "/redirected":
                self.send_response(302)
                self.send_header("Location", "/page")
                self.end_headers()

                return

            if path == "/missing":
                self.send_error(404)

                return

            if path == "/slow":
                body = b"<!doctype html><html><body><h1>Slow response</h1></body></html>"
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body[:20])
                self.wfile.flush()
                time.sleep(0.5)
                self.wfile.write(body[20:])

                return

            if path == "/redirect-to-pdf":
                self.send_response(302)
                self.send_header("Location", "/assets/document.pdf")
                self.end_headers()

                return

            if path == "/redirect-to-download":
                self.send_response(302)
                self.send_header("Location", "/assets/download.bin")
                self.end_headers()

                return

            if path == "/page":
                self._write(PAGE.encode(), "text/html; charset=utf-8")

                return

            if path in CAPTURE_PAGES:
                page = PAGE.replace("Recorder acceptance page", CAPTURE_PAGES[path])
                self._write(page.encode(), "text/html; charset=utf-8")

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

            if path == "/assets/document.pdf":
                self._write(PDF, "application/pdf")

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

    return LocalSite(
        server=server,
        thread=thread,
        base_url=f"http://{HOST}:{server.server_port}",
    )


@dataclass
class ReplayResult:
    status_code: int
    page_title: str
    page_state: str
    download_content: str
    image_width: int
    body_font_family: str


async def replay_page(capture_dir: Path, replay_dir: Path, page_url: str) -> ReplayResult:
    replay_server = PyWBReplayServer(capture_dir, replay_dir)

    await replay_server.start()

    try:
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(headless=True)

            try:
                page = await browser.new_page()
                response = await page.goto(
                    replay_server.replay_url(page_url),
                    wait_until="domcontentloaded",
                )

                if response is None:
                    raise RuntimeError("Replay navigation did not return a response")

                await page.wait_for_function(
                    "document.querySelector('#download')?.textContent === "
                    "'archive-download-payload'"
                )

                return ReplayResult(
                    status_code=response.status,
                    page_title=await page.title(),
                    page_state=await page.locator("#state").inner_text(),
                    download_content=await page.locator("#download").inner_text(),
                    image_width=await page.locator("img").evaluate("(image) => image.naturalWidth"),
                    body_font_family=await page.locator("body").evaluate(
                        "(body) => getComputedStyle(body).fontFamily"
                    ),
                )
            finally:
                await browser.close()
    finally:
        await replay_server.stop()
