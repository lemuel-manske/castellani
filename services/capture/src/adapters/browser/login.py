import asyncio
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, cast

from playwright.async_api import Browser, BrowserContext, Playwright, async_playwright

from domain.login import BrowserEndpoint
from ports.login import InteractiveBrowser
from utils.web import is_safe_request_url, is_valid_url

VIEWPORT_WIDTH = 1365
VIEWPORT_HEIGHT = 768

PROCESS_STOP_TIMEOUT_SECONDS = 3

DISPLAY_POLL_INTERVAL_SECONDS = 0.05

DISPLAY_START_ATTEMPTS = 100

DEFAULT_NOVNC_ROOT = "/usr/share/novnc"


@dataclass(frozen=True)
class LoginBrowserSettings:
    display_start: int
    vnc_port_start: int
    websockify_port_start: int
    max_sessions: int
    novnc_root: str = DEFAULT_NOVNC_ROOT


@dataclass(frozen=True)
class LoginBrowserSession:
    session_id: str
    display: str
    rfb_port: int
    websocket_port: int
    vnc_origin: str


@dataclass(frozen=True)
class StartedBrowser:
    session: LoginBrowserSession
    playwright: Playwright
    browser: Browser
    context: BrowserContext
    processes: tuple[asyncio.subprocess.Process, ...]


class LiveLoginSession:
    def __init__(self, started: StartedBrowser, slot: int) -> None:
        self.session = started.session
        self.playwright = started.playwright
        self.browser = started.browser
        self.context = started.context
        self.processes = started.processes
        self.slot = slot


class PlaywrightLoginBrowser(InteractiveBrowser):
    def __init__(self, settings: LoginBrowserSettings) -> None:
        self.settings = settings
        self.sessions: dict[str, LiveLoginSession] = {}
        self.free_slots = list(range(settings.max_sessions))
        self.lock = asyncio.Lock()

    async def start(self, session_id: str, target_url: str) -> BrowserEndpoint:
        if not is_valid_url(target_url) or not await is_safe_request_url(target_url):
            raise ValueError("target URL is not safe for interactive navigation")

        async with self.lock:
            if session_id in self.sessions:
                raise ValueError("session already has a live browser")

            if not self.free_slots:
                raise RuntimeError("interactive login capacity is exhausted")

            slot = self.free_slots.pop(0)

        try:
            started = await self._start(slot, session_id, target_url)
        except Exception:
            async with self.lock:
                if slot not in self.free_slots:
                    self.free_slots.append(slot)
                    self.free_slots.sort()

            raise

        async with self.lock:
            self.sessions[session_id] = LiveLoginSession(started, slot)

        return BrowserEndpoint(
            session_id=session_id,
            vnc_origin=started.session.vnc_origin,
        )

    async def storage_state(self, session_id: str) -> dict[str, Any]:
        live = self.sessions.get(session_id)

        if live is None:
            raise ValueError("session has no live browser")

        state = cast(dict[str, Any], await live.context.storage_state())

        return state

    async def close(self, session_id: str) -> None:
        async with self.lock:
            live = self.sessions.pop(session_id, None)

        if live is not None:
            await self._close(live)

    async def close_all(self) -> None:
        async with self.lock:
            live_sessions = tuple(self.sessions.values())
            self.sessions.clear()

        for live in live_sessions:
            await self._close(live)

    async def _start(self, slot: int, session_id: str, target_url: str) -> StartedBrowser:
        display_number = self.settings.display_start + slot
        display = f":{display_number}"
        rfb_port = self.settings.vnc_port_start + slot
        websocket_port = self.settings.websockify_port_start + slot

        processes: list[asyncio.subprocess.Process] = []

        try:
            processes.append(
                await asyncio.create_subprocess_exec(
                    "Xvfb",
                    display,
                    "-screen",
                    "0",
                    f"{VIEWPORT_WIDTH}x{VIEWPORT_HEIGHT}x24",
                    "-nolisten",
                    "tcp",
                    stdout=asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.DEVNULL,
                )
            )

            await wait_for_display(display_number)

            processes.append(
                await asyncio.create_subprocess_exec(
                    "x11vnc",
                    "-display",
                    display,
                    "-forever",
                    "-shared",
                    "-rfbport",
                    str(rfb_port),
                    "-listen",
                    "127.0.0.1",
                    "-nopw",
                    stdout=asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.DEVNULL,
                )
            )

            processes.append(
                await asyncio.create_subprocess_exec(
                    "websockify",
                    "--web",
                    self.settings.novnc_root,
                    str(websocket_port),
                    f"127.0.0.1:{rfb_port}",
                    stdout=asyncio.subprocess.DEVNULL,
                    stderr=asyncio.subprocess.DEVNULL,
                )
            )

            playwright = await async_playwright().start()

            try:
                browser = await playwright.chromium.launch(
                    headless=False,
                    env={**os.environ, "DISPLAY": display},
                    args=["--no-sandbox", "--disable-dev-shm-usage"],
                )

                context = await browser.new_context(
                    viewport={
                        "width": VIEWPORT_WIDTH,
                        "height": VIEWPORT_HEIGHT,
                    },
                    ignore_https_errors=True,
                )

                page = await context.new_page()
                await page.goto(target_url, wait_until="domcontentloaded")
            except Exception:
                await playwright.stop()
                raise
        except Exception:
            await stop_processes(tuple(processes))
            raise

        return StartedBrowser(
            session=LoginBrowserSession(
                session_id=session_id,
                display=display,
                rfb_port=rfb_port,
                websocket_port=websocket_port,
                vnc_origin=f"http://127.0.0.1:{websocket_port}",
            ),
            playwright=playwright,
            browser=browser,
            context=context,
            processes=tuple(processes),
        )

    async def _close(self, live: LiveLoginSession) -> None:
        try:
            await live.context.close()
        finally:
            try:
                await live.browser.close()
            finally:
                try:
                    await live.playwright.stop()
                finally:
                    await stop_processes(live.processes)

                    async with self.lock:
                        if live.slot not in self.free_slots:
                            self.free_slots.append(live.slot)
                            self.free_slots.sort()


async def wait_for_display(display_number: int) -> None:
    socket_path = Path(f"/tmp/.X11-unix/X{display_number}")

    for _ in range(DISPLAY_START_ATTEMPTS):
        if socket_path.exists():
            return

        await asyncio.sleep(DISPLAY_POLL_INTERVAL_SECONDS)

    raise RuntimeError(f"X display :{display_number} did not start")


async def stop_processes(processes: tuple[asyncio.subprocess.Process, ...]) -> None:
    for process in reversed(processes):
        if process.returncode is not None:
            continue

        process.terminate()

    for process in reversed(processes):
        if process.returncode is not None:
            continue

        try:
            await asyncio.wait_for(process.wait(), timeout=PROCESS_STOP_TIMEOUT_SECONDS)
        except TimeoutError:
            process.kill()
            await process.wait()
