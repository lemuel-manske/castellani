import asyncio
import json
import signal
import socket
from collections.abc import Callable
from pathlib import Path

import httpx

from utils.template import template

HOST = "127.0.0.1"

COLLECTION_NAME = "capture"

CA_DOWNLOAD_PATH = "/wsgiprox/download/pem"

PROCESS_SHUTDOWN_TIMEOUT_SECONDS = 10
STARTUP_TIMEOUT_SECONDS = 15

RECORD_CONFIG_TEMPLATE = """
collections_root: {{ROOT}}
archive_paths:
  - archive
index_paths:
  - indexes
collections:
  live: "$live"
proxy:
  coll: {{COLLECTION_NAME}}
  recording: true
  ca_file_cache: {{CA_FILE_CACHE}}
  enable_content_rewrite: false
recorder:
  source_coll: live
  filename_template: "capture-{{timestamp}}-{{hostname}}-{{random}}.warc.gz"
"""

REPLAY_CONFIG_TEMPLATE = """
collections_root: {{ROOT}}
archive_paths:
  - archive
index_paths:
  - indexes
framed_replay: false
"""


def available_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind((HOST, 0))

        return int(listener.getsockname()[1])


async def wait_for_http_response(
    process: asyncio.subprocess.Process,
    url: str,
    is_ready: Callable[[httpx.Response], bool] | None = None,
) -> httpx.Response:
    deadline = asyncio.get_running_loop().time() + STARTUP_TIMEOUT_SECONDS

    async with httpx.AsyncClient(trust_env=False, timeout=1) as client:
        while asyncio.get_running_loop().time() < deadline:
            if process.returncode is not None:
                raise RuntimeError("pywb process exited before becoming ready")

            try:
                response = await client.get(url)
            except httpx.TransportError:
                await asyncio.sleep(0.1)

                continue

            if is_ready is None or is_ready(response):
                return response

            await asyncio.sleep(0.1)

    raise TimeoutError("pywb process did not become ready in time")


async def stop_process(process: asyncio.subprocess.Process) -> None:
    if process.returncode is not None:
        return

    process.send_signal(signal.SIGINT)

    try:
        await asyncio.wait_for(
            process.wait(),
            timeout=PROCESS_SHUTDOWN_TIMEOUT_SECONDS,
        )
    except TimeoutError:
        process.kill()
        await process.wait()


class PyWBRecorder:
    def __init__(self, output_dir: Path) -> None:
        self.output_dir = output_dir
        self.collections_dir = output_dir / "collections"
        self.ca_certificate_path = output_dir / "proxy-certs" / "pywb-ca.pem"
        self.archive_dir = output_dir / "collections" / COLLECTION_NAME / "archive"
        self.config_path = output_dir / "config.yaml"

        self.port = available_port()

        self.process: asyncio.subprocess.Process | None = None

    @property
    def proxy_url(self) -> str:
        return f"http://{HOST}:{self.port}"

    @property
    def warc_files(self) -> tuple[Path, ...]:
        wacz_files = self.archive_dir.glob("*.warc.gz")

        return tuple(sorted(wacz_files))

    async def start(self) -> "PyWBRecorder":
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self.ca_certificate_path.parent.mkdir(parents=True, exist_ok=True)

        self._write_config()
        await self._initialize_collection()

        self.process = await asyncio.create_subprocess_exec(
            "wayback",
            "--proxy",
            COLLECTION_NAME,
            "-p",
            str(self.port),
            cwd=self.output_dir,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )

        try:
            await self._wait_until_ready()
        except BaseException:
            await self.stop()
            raise

        return self

    async def stop(self) -> None:
        if self.process is None:
            return

        await stop_process(self.process)

    def _write_config(self) -> None:
        config = (
            template(RECORD_CONFIG_TEMPLATE)
            .r("ROOT", json.dumps(str(self.collections_dir)))
            .r("COLLECTION_NAME", COLLECTION_NAME)
            .r("CA_FILE_CACHE", json.dumps(str(self.ca_certificate_path)))
        )

        self.config_path.write_text(str(config), encoding="utf-8")

    async def _initialize_collection(self) -> None:
        process = await asyncio.create_subprocess_exec(
            "wb-manager",
            "init",
            COLLECTION_NAME,
            cwd=self.output_dir,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )

        result = await process.wait()

        if result != 0:
            raise RuntimeError("pywb could not initialize the recording collection")

    async def _wait_until_ready(self) -> None:
        process = self.process

        if process is None:
            raise RuntimeError("pywb recorder process has not started")

        response = await wait_for_http_response(
            process,
            f"{self.proxy_url}{CA_DOWNLOAD_PATH}",
            lambda response: (
                response.status_code == 200 and b"BEGIN CERTIFICATE" in response.content
            ),
        )

        self.ca_certificate_path.write_bytes(response.content)


class PyWBReplayServer:
    def __init__(self, capture_dir: Path, replay_dir: Path) -> None:
        self.capture_dir = capture_dir
        self.replay_dir = replay_dir

        self.collections_dir = capture_dir / "collections"
        self.config_path = replay_dir / "config.yaml"

        self.port = available_port()

        self.process: asyncio.subprocess.Process | None = None

    def replay_url(self, page_url: str) -> str:
        return f"http://{HOST}:{self.port}/{COLLECTION_NAME}/{page_url}"

    async def start(self) -> "PyWBReplayServer":
        await self._reindex_collection()

        self.replay_dir.mkdir(parents=True, exist_ok=True)

        self._write_config()

        self.process = await asyncio.create_subprocess_exec(
            "wayback",
            "-p",
            str(self.port),
            cwd=self.replay_dir,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )

        try:
            process = self.process

            if not process:
                raise RuntimeError("pywb replay process has not started")

            await wait_for_http_response(process, f"http://{HOST}:{self.port}/")
        except BaseException:
            await self.stop()

            raise

        return self

    async def stop(self) -> None:
        process = self.process

        if process is None:
            return

        await stop_process(process)

    def _write_config(self) -> None:
        replay_config = template(REPLAY_CONFIG_TEMPLATE).r("ROOT", str(self.collections_dir))

        self.config_path.write_text(str(replay_config), encoding="utf-8")

    async def _reindex_collection(self) -> None:
        process = await asyncio.create_subprocess_exec(
            "wb-manager",
            "reindex",
            COLLECTION_NAME,
            cwd=self.capture_dir,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )

        result = await process.wait()

        if result != 0:
            raise RuntimeError("pywb could not reindex the recording collection")
