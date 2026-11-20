import asyncio
import ipaddress
import os
import socket
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urljoin, urlsplit

from playwright.async_api import Route, TimeoutError as PlaywrightTimeoutError, async_playwright
from selectolax.parser import HTMLParser

from capture.recording import PyWBRecorder

NAVIGATION_TIMEOUT_MILLISECONDS = 30_000
NETWORK_IDLE_TIMEOUT_MILLISECONDS = 5_000
VIEWPORT_WIDTH = 1365
VIEWPORT_HEIGHT = 768

HTTP_SCHEMES = {"http", "https"}
DEFAULT_MAX_REQUESTS = 500
DEFAULT_MAX_DOCUMENT_BYTES = 5 * 1024 * 1024
DEFAULT_MAX_DISCOVERED_LINKS = 1_000


@dataclass(frozen=True)
class CaptureLimits:
    navigation_timeout_milliseconds: int = NAVIGATION_TIMEOUT_MILLISECONDS
    network_idle_timeout_milliseconds: int = NETWORK_IDLE_TIMEOUT_MILLISECONDS
    max_requests: int = DEFAULT_MAX_REQUESTS
    max_document_bytes: int = DEFAULT_MAX_DOCUMENT_BYTES
    max_discovered_links: int = DEFAULT_MAX_DISCOVERED_LINKS
    allow_private_networks: bool = False


@dataclass(frozen=True)
class PageCapture:
    requested_url: str
    final_url: str
    status_code: int | None
    content_type: str | None
    title: str
    captured_at: datetime
    discovered_urls: tuple[str, ...]
    blocked_urls: tuple[str, ...]
    warc_files: tuple[Path, ...]


class CaptureLimitExceeded(RuntimeError):
    pass


class UnsafeCaptureRequest(RuntimeError):
    pass


class RequestGuard:
    def __init__(self, limits: CaptureLimits) -> None:
        self.limits = limits
        self.request_count = 0
        self.blocked_urls: list[str] = []
        self.blocked_navigation_url: str | None = None
        self.request_limit_exceeded = False

    async def handle(self, route: Route) -> None:
        request = route.request

        if self.request_count >= self.limits.max_requests:
            self.request_limit_exceeded = True
            await route.abort()
            return

        if not await is_safe_request_url(
            request.url,
            allow_private_networks=self.limits.allow_private_networks,
        ):
            self.blocked_urls.append(request.url)

            if request.is_navigation_request():
                self.blocked_navigation_url = request.url

            await route.abort()
            return

        self.request_count += 1
        await route.continue_()

    def raise_if_rejected(self) -> None:
        if self.request_limit_exceeded:
            raise CaptureLimitExceeded(
                f"capture exceeded the request limit of {self.limits.max_requests}"
            )

        if self.blocked_navigation_url is not None:
            raise UnsafeCaptureRequest(
                f"navigation to a disallowed URL was blocked: {self.blocked_navigation_url}"
            )


def extract_links(
    html: str,
    base_url: str,
    max_links: int = DEFAULT_MAX_DISCOVERED_LINKS,
) -> tuple[str, ...]:
    document = HTMLParser(html)
    discovered: dict[str, None] = {}

    for anchor in document.css("a[href]"):
        href = anchor.attributes.get("href", "")

        if not href:
            continue

        href = href.strip()

        try:
            absolute_url = urljoin(base_url, href)
        except ValueError:
            continue

        if not is_valid_url(absolute_url) or absolute_url in discovered:
            continue

        if len(discovered) >= max_links:
            raise CaptureLimitExceeded(
                f"page exceeded the discovered-link limit of {max_links}"
            )

        discovered.setdefault(absolute_url, None)

    return tuple(discovered)


async def capture_page(
    url: str,
    output_dir: Path,
    limits: CaptureLimits | None = None,
) -> PageCapture:
    limits = limits or CaptureLimits()

    if not is_valid_url(url):
        raise ValueError("capture URL must be an absolute HTTP or HTTPS URL without credentials")

    recorder = PyWBRecorder(output_dir)

    await recorder.start()

    try:
        browser_home = output_dir / "browser-home"
        browser_profile = output_dir / "browser-profile"

        await trust_certificate(recorder.ca_certificate_path, browser_home)

        async with async_playwright() as playwright:
            context = await playwright.chromium.launch_persistent_context(
                headless=True,
                user_data_dir=browser_profile,
                proxy={"server": recorder.proxy_url},
                env={**os.environ, "HOME": str(browser_home)},
                viewport={"width": VIEWPORT_WIDTH, "height": VIEWPORT_HEIGHT},
                service_workers="block",
            )

            try:
                request_guard = RequestGuard(limits)
                await context.route("**/*", request_guard.handle)

                page = context.pages[0] if context.pages else await context.new_page()

                try:
                    response = await page.goto(
                        url,
                        wait_until="domcontentloaded",
                        timeout=limits.navigation_timeout_milliseconds,
                    )
                except Exception:
                    request_guard.raise_if_rejected()
                    raise

                request_guard.raise_if_rejected()

                try:
                    await page.wait_for_load_state(
                        "networkidle",
                        timeout=limits.network_idle_timeout_milliseconds,
                    )
                except PlaywrightTimeoutError:
                    pass

                request_guard.raise_if_rejected()

                document_bytes = await page.evaluate(
                    "() => new TextEncoder().encode("
                    "document.documentElement?.outerHTML ?? '').byteLength"
                )

                if document_bytes > limits.max_document_bytes:
                    raise CaptureLimitExceeded(
                        "page document exceeded the "
                        f"{limits.max_document_bytes}-byte limit"
                    )

                html = await page.content()
                title = await page.title()

                if response:
                    content_type = response.headers.get("content-type")
                    status_code = response.status
                else:
                    content_type = None
                    status_code = None

                final_url = page.url
                discovered_urls = extract_links(
                    html,
                    final_url,
                    max_links=limits.max_discovered_links,
                )
                captured_at = datetime.now(UTC)
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
        blocked_urls=tuple(request_guard.blocked_urls),
        warc_files=warc_files,
    )


async def is_safe_request_url(url: str, allow_private_networks: bool = False) -> bool:
    if not is_valid_url(url):
        return False

    if allow_private_networks:
        return True

    parsed_url = urlsplit(url)
    hostname = parsed_url.hostname

    if hostname is None:
        return False

    try:
        address = ipaddress.ip_address(hostname)
    except ValueError:
        port = parsed_url.port or (443 if parsed_url.scheme == "https" else 80)

        try:
            records = await asyncio.get_running_loop().getaddrinfo(
                hostname,
                port,
                type=socket.SOCK_STREAM,
            )
        except OSError:
            return False

        addresses = {ipaddress.ip_address(record[4][0]) for record in records}

        return bool(addresses) and all(address.is_global for address in addresses)

    return address.is_global


async def trust_certificate(certificate_path: Path, browser_home: Path) -> None:
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


def is_valid_url(url: str) -> bool:
    try:
        parsed_url = urlsplit(url)

        if (
            parsed_url.scheme not in HTTP_SCHEMES
            or not parsed_url.hostname
            or parsed_url.username is not None
            or parsed_url.password is not None
        ):
            return False

        port = parsed_url.port

        if port is not None and not 0 <= port <= 65_535:
            return False
    except ValueError:
        return False

    return True
