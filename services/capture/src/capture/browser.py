import asyncio
import os
import subprocess
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from pathlib import Path
from urllib.parse import urljoin

from playwright.async_api import (
    Download,
    Request,
    Response,
    Route,
    async_playwright,
)
from playwright.async_api import (
    Error as PlaywrightError,
)
from playwright.async_api import TimeoutError as PlaywrightTimeoutError
from selectolax.parser import HTMLParser

from capture.recording import PyWBRecorder
from utils.http import is_safe_request_url, is_valid_url
from utils.tasks import complete_before_cancellation
from utils.web import is_html_content_type, is_pdf_content_type

NAVIGATION_TIMEOUT_MILLISECONDS = 30_000
NETWORK_IDLE_TIMEOUT_MILLISECONDS = 5_000
VIEWPORT_WIDTH = 1365
VIEWPORT_HEIGHT = 768

DEFAULT_MAX_REQUESTS = 500
DEFAULT_MAX_DOCUMENT_BYTES = 5 * 1024 * 1024
DEFAULT_MAX_DISCOVERED_LINKS = 1_000
DEFAULT_ALLOW_PRIVATE_NETWORKS = False
DOWNLOAD_EVENT_TIMEOUT_SECONDS = 2


@dataclass(frozen=True)
class CaptureLimits:
    navigation_timeout_milliseconds: int = NAVIGATION_TIMEOUT_MILLISECONDS
    network_idle_timeout_milliseconds: int = NETWORK_IDLE_TIMEOUT_MILLISECONDS
    max_requests: int = DEFAULT_MAX_REQUESTS
    max_document_bytes: int = DEFAULT_MAX_DOCUMENT_BYTES
    max_discovered_links: int = DEFAULT_MAX_DISCOVERED_LINKS
    allow_private_networks: bool = DEFAULT_ALLOW_PRIVATE_NETWORKS


DEFAULT_LIMITS = CaptureLimits()


@dataclass(frozen=True)
class PageCapture:
    requested_url: str
    final_url: str
    redirect_chain: tuple[str, ...]
    status_code: int | None
    content_type: str | None
    title: str
    captured_at: datetime
    discovered_urls: tuple[str, ...]
    blocked_urls: tuple[str, ...]
    warc_files: tuple[Path, ...]


class CaptureFailureCode(StrEnum):
    INVALID_URL = "invalid_url"
    UNSAFE_REQUEST = "unsafe_request"
    REQUEST_LIMIT_EXCEEDED = "request_limit_exceeded"
    DOCUMENT_LIMIT_EXCEEDED = "document_limit_exceeded"
    DISCOVERED_LINK_LIMIT_EXCEEDED = "discovered_link_limit_exceeded"
    NAVIGATION_FAILED = "navigation_failed"
    DOWNLOAD_FAILED = "download_failed"
    RECORDING_FAILED = "recording_failed"


class CaptureFailure(RuntimeError):
    def __init__(self, reason_code: CaptureFailureCode, message: str) -> None:
        super().__init__(message)

        self.reason_code = reason_code


class CaptureLimitExceeded(CaptureFailure):
    pass


class UnsafeCaptureRequest(CaptureFailure):
    def __init__(self, message: str) -> None:
        super().__init__(CaptureFailureCode.UNSAFE_REQUEST, message)


class InvalidCaptureURL(ValueError):
    reason_code = CaptureFailureCode.INVALID_URL


class CaptureNavigationFailed(CaptureFailure):
    def __init__(self, message: str) -> None:
        super().__init__(CaptureFailureCode.NAVIGATION_FAILED, message)


class CaptureDownloadFailed(CaptureFailure):
    def __init__(self, message: str) -> None:
        super().__init__(CaptureFailureCode.DOWNLOAD_FAILED, message)


class CaptureRecordingFailed(CaptureFailure):
    def __init__(self, message: str) -> None:
        super().__init__(CaptureFailureCode.RECORDING_FAILED, message)


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
                CaptureFailureCode.REQUEST_LIMIT_EXCEEDED,
                f"capture exceeded the request limit of {self.limits.max_requests}",
            )

        if self.blocked_navigation_url is not None:
            raise UnsafeCaptureRequest(
                f"navigation to a disallowed URL was blocked: {self.blocked_navigation_url}"
            )


def extract_redirect_chain(request: Request) -> tuple[str, ...]:
    chain: list[str] = []
    current: Request | None = request

    while current is not None:
        chain.append(current.url)
        current = current.redirected_from

    return tuple(reversed(chain))


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
                CaptureFailureCode.DISCOVERED_LINK_LIMIT_EXCEEDED,
                f"page exceeded the discovered-link limit of {max_links}",
            )

        discovered.setdefault(absolute_url, None)

    return tuple(discovered)


async def capture_local_page(url: str, output_dir: Path) -> PageCapture:
    return await capture_page(
        url,
        output_dir,
        limits=CaptureLimits(allow_private_networks=True),
    )


async def capture_page(
    url: str, output_dir: Path, limits: CaptureLimits = DEFAULT_LIMITS
) -> PageCapture:
    if not is_valid_url(url):
        raise InvalidCaptureURL(
            "capture URL must be an absolute HTTP or HTTPS URL without credentials"
        )

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

                loop = asyncio.get_running_loop()
                download_future: asyncio.Future[Download] = loop.create_future()

                main_request_finished = asyncio.Event()

                main_response_future: asyncio.Future[Response] = loop.create_future()

                def record_download(download: Download) -> None:
                    if not download_future.done():
                        download_future.set_result(download)

                def record_main_response(response: Response) -> None:
                    request = response.request

                    if (
                        request.is_navigation_request()
                        and request.frame == page.main_frame
                        and not main_response_future.done()
                    ):
                        main_response_future.set_result(response)

                def record_main_request_finished(request: Request) -> None:
                    if request.is_navigation_request() and request.frame == page.main_frame:
                        main_request_finished.set()

                page.on("download", record_download)
                page.on("response", record_main_response)
                page.on("requestfinished", record_main_request_finished)

                try:
                    try:
                        response = await page.goto(
                            url,
                            wait_until="domcontentloaded",
                            timeout=limits.navigation_timeout_milliseconds,
                        )
                    except PlaywrightError as navigation_error:
                        request_guard.raise_if_rejected()

                        if not download_future.done():
                            try:
                                await asyncio.wait_for(
                                    asyncio.shield(download_future),
                                    timeout=DOWNLOAD_EVENT_TIMEOUT_SECONDS,
                                )
                            except TimeoutError:
                                pass

                        if download_future.done():
                            download = download_future.result()
                            final_url = download.url

                            response = (
                                main_response_future.result()
                                if main_response_future.done()
                                else None
                            )
                        elif (
                            main_response_future.done()
                            and is_pdf_content_type(
                                main_response_future.result().headers.get("content-type")
                            )
                        ):
                            try:
                                await asyncio.wait_for(
                                    main_request_finished.wait(),
                                    timeout=DOWNLOAD_EVENT_TIMEOUT_SECONDS,
                                )
                            except TimeoutError:
                                raise CaptureNavigationFailed(
                                    "browser did not finish the PDF navigation response"
                                ) from navigation_error

                            response = main_response_future.result()
                            final_url = response.url
                        else:
                            raise CaptureNavigationFailed(
                                "browser navigation did not produce a document or downloadable resource"
                            ) from navigation_error
                    else:
                        response = response or (
                            main_response_future.result()
                            if main_response_future.done()
                            else None
                        )
                        final_url = page.url

                    if (
                        response is not None
                        and "attachment" in response.headers.get("content-disposition", "").lower()
                        and not download_future.done()
                    ):
                        try:
                            await asyncio.wait_for(
                                asyncio.shield(download_future),
                                timeout=DOWNLOAD_EVENT_TIMEOUT_SECONDS,
                            )
                        except TimeoutError as error:
                            raise CaptureDownloadFailed(
                                "browser did not complete the attachment download"
                            ) from error

                    if download_future.done():
                        download = download_future.result()
                        final_url = download.url

                        await download.path()

                    request_guard.raise_if_rejected()

                    redirect_chain = (
                        extract_redirect_chain(response.request) if response is not None else ()
                    )

                    if response:
                        content_type = response.headers.get("content-type")
                        status_code = response.status
                    else:
                        content_type = None
                        status_code = None

                    if is_html_content_type(content_type) and not download_future.done():
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
                                CaptureFailureCode.DOCUMENT_LIMIT_EXCEEDED,
                                f"page document exceeded the {limits.max_document_bytes}-byte limit",
                            )

                        html = await page.content()
                        title = await page.title()

                        discovered_urls = extract_links(
                            html,
                            final_url,
                            max_links=limits.max_discovered_links,
                        )
                    else:
                        title = ""

                        discovered_urls = ()

                    captured_at = datetime.now(UTC)
                finally:
                    page.remove_listener("download", record_download)
                    page.remove_listener("response", record_main_response)
                    page.remove_listener("requestfinished", record_main_request_finished)

                    if not download_future.done():
                        download_future.cancel()
            finally:
                await complete_before_cancellation(context.close())
    finally:
        await complete_before_cancellation(recorder.stop())

    warc_files = recorder.warc_files

    if not warc_files:
        raise CaptureRecordingFailed("pywb recorder produced no WARC artifacts")

    return PageCapture(
        requested_url=url,
        final_url=final_url,
        redirect_chain=redirect_chain,
        status_code=status_code,
        content_type=content_type,
        title=title,
        captured_at=captured_at,
        discovered_urls=discovered_urls,
        blocked_urls=tuple(request_guard.blocked_urls),
        warc_files=warc_files,
    )


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
