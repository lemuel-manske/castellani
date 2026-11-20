import asyncio
import os
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlsplit

from playwright.async_api import TimeoutError as PlaywrightTimeoutError
from playwright.async_api import async_playwright
from selectolax.parser import HTMLParser

from capture.recording import PyWBRecorder

NAVIGATION_TIMEOUT_MILLISECONDS = 30_000
NETWORK_IDLE_TIMEOUT_MILLISECONDS = 5_000
VIEWPORT_WIDTH = 1365
VIEWPORT_HEIGHT = 768


@dataclass(frozen=True)
class PageCapture:
    requested_url: str
    final_url: str
    status_code: int | None
    content_type: str | None
    title: str
    captured_at: datetime
    discovered_urls: tuple[str, ...]
    warc_files: tuple[Path, ...]


def extract_links(html: str, base_url: str) -> tuple[str, ...]:
    document = HTMLParser(html)
    discovered: dict[str, None] = {}

    for anchor in document.css("a[href]"):
        href = anchor.attributes.get("href", "").strip()

        if not href:
            continue

        absolute_url = urljoin(base_url, href)
        parsed_url = urlsplit(absolute_url)

        if parsed_url.scheme not in {"http", "https"} or not parsed_url.netloc:
            continue

        discovered.setdefault(absolute_url, None)

    return tuple(discovered)


async def capture_page(url: str, output_dir: Path) -> PageCapture:
    parsed_url = urlsplit(url)

    if parsed_url.scheme not in {"http", "https"} or not parsed_url.netloc:
        raise ValueError("capture URL must be an absolute HTTP or HTTPS URL")

    recorder = await PyWBRecorder(output_dir).start()

    try:
        browser_home = output_dir / "browser-home"
        await _trust_recorder_certificate(recorder.ca_certificate_path, browser_home)

        async with async_playwright() as playwright:
            context = await playwright.chromium.launch_persistent_context(
                user_data_dir=str(output_dir / "browser-profile"),
                headless=True,
                proxy={"server": recorder.proxy_url},
                env={**os.environ, "HOME": str(browser_home)},
                viewport={"width": VIEWPORT_WIDTH, "height": VIEWPORT_HEIGHT},
            )

            try:
                page = context.pages[0] if context.pages else await context.new_page()
                response = await page.goto(
                    url,
                    wait_until="domcontentloaded",
                    timeout=NAVIGATION_TIMEOUT_MILLISECONDS,
                )

                try:
                    await page.wait_for_load_state(
                        "networkidle",
                        timeout=NETWORK_IDLE_TIMEOUT_MILLISECONDS,
                    )
                except PlaywrightTimeoutError:
                    pass

                html = await page.content()
                final_url = page.url
                content_type = response.headers.get("content-type") if response else None
                status_code = response.status if response else None
                title = await page.title()
                discovered_urls = extract_links(html, final_url)
                captured_at = datetime.now(timezone.utc)
            finally:
                await context.close()
    finally:
        await recorder.stop()

    warc_files = recorder.warc_files

    if not warc_files:
        raise RuntimeError("pywb recorder produced no WARC artifacts")

    return PageCapture(
        requested_url=url,
        final_url=final_url,
        status_code=status_code,
        content_type=content_type,
        title=title,
        captured_at=captured_at,
        discovered_urls=discovered_urls,
        warc_files=warc_files,
    )


async def _trust_recorder_certificate(certificate_path: Path, browser_home: Path) -> None:
    database_path = browser_home / ".pki" / "nssdb"
    database_path.mkdir(parents=True, exist_ok=True)
    database_uri = f"sql:{database_path}"

    await asyncio.to_thread(
        subprocess.run,
        ["certutil", "-N", "-d", database_uri, "--empty-password"],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )
    await asyncio.to_thread(
        subprocess.run,
        [
            "certutil",
            "-A",
            "-d",
            database_uri,
            "-n",
            "Castellani Capture Recorder",
            "-t",
            "C,,",
            "-i",
            str(certificate_path),
        ],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )
