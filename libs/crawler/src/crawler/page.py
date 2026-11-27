import asyncio
import json
import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

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
from playwright.async_api import (
    TimeoutError as PlaywrightTimeoutError,
)

from .fn import (
    complete_before_cancellation,
    is_html_content_type,
    is_pdf_content_type,
    is_safe_url,
    is_valid_url,
)
from .links import extract_links
from .recording import PyWBRecorder
from .results import (
    BrowserCaptureResult,
    CaptureDownloadFailed,
    CaptureLimits,
    CaptureNavigationFailed,
    CaptureRecordingFailed,
    DocumentLimitExceeded,
    InvalidCaptureURL,
    RequestLimitExceeded,
    UnsafeCaptureRequest,
)
from .utils import trust_certificate

VIEWPORT_WIDTH = 1365
VIEWPORT_HEIGHT = 768

DEFAULT_LIMITS = CaptureLimits()

DOWNLOAD_EVENT_TIMEOUT_SECONDS = 2


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

        if not await is_safe_url(
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
            raise RequestLimitExceeded(
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


async def apply_storage_state(context: Any, state: dict[str, Any]) -> None:
    cookies = state.get("cookies", [])

    if cookies:
        await context.add_cookies(cookies)

    origins = state.get("origins", [])

    if not origins:
        return

    payload = json.dumps(origins, separators=(",", ":"))

    script = f"""(() => {{
        const origins = {payload};

        for (const entry of origins) {{
            if (window.location.origin !== entry.origin) {{
                continue;
            }}

            for (const item of entry.localStorage) {{
                try {{
                    window.localStorage.setItem(item.name, item.value);
                }} catch (error) {{
                    continue;
                }}
            }}
        }}
    }})()"""

    await context.add_init_script(script=script)


async def capture_page(
    url: str,
    output_dir: Path,
    limits: CaptureLimits = DEFAULT_LIMITS,
    storage_state: dict[str, Any] | None = None,
) -> BrowserCaptureResult:
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

            if storage_state is not None:
                await apply_storage_state(context, storage_state)

            try:
                request_guard = RequestGuard(limits)
                await context.route("**/*", request_guard.handle)

                page = context.pages[0] if context.pages else await context.new_page()

                loop = asyncio.get_running_loop()
                download_future: asyncio.Future[Download] = loop.create_future()

                main_request_finished = asyncio.Event()

                main_responses: list[Response] = []

                def record_download(download: Download) -> None:
                    if not download_future.done():
                        download_future.set_result(download)

                def record_main_response(response: Response) -> None:
                    request = response.request

                    if request.is_navigation_request() and request.frame == page.main_frame:
                        main_responses.append(response)

                def record_main_request_finished(request: Request) -> None:
                    if (
                        request.is_navigation_request()
                        and request.frame == page.main_frame
                        and request.redirected_to is None
                    ):
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

                            response = main_responses[-1] if main_responses else None
                        elif main_responses and is_pdf_content_type(
                            main_responses[-1].headers.get("content-type")
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

                            response = main_responses[-1]
                            final_url = response.url
                        else:
                            msg = (
                                "browser navigation did not produce "
                                "a document or downloadable resource"
                            )

                            raise CaptureNavigationFailed(msg) from navigation_error
                    else:
                        response = response or (main_responses[-1] if main_responses else None)
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
                            msg = (
                                "page document exceeded the {limits.max_document_bytes}-byte limit"
                            )

                            raise DocumentLimitExceeded(msg)

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

    return BrowserCaptureResult(
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


__all__ = [
    "capture_page",
]
