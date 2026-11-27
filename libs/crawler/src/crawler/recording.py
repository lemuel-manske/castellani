import asyncio
import json
from pathlib import Path

from .fn import available_port, stop_process, template, wait_for_http_response, wait_for_process

COLLECTION_NAME = "capture"

HOST = "127.0.0.1"

RECORD_CONFIG_TEMPLATE = """
collections_root: {{ROOT}}
archive_paths: archive
index_paths: indexes
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
archive_paths: archive
index_paths: indexes
framed_replay: false
"""


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
        )

        result = await wait_for_process(process)

        if result != 0:
            raise RuntimeError("pywb could not initialize the recording collection")

    async def _wait_until_ready(self) -> None:
        process = self.process

        if process is None:
            raise RuntimeError("pywb recorder process has not started")

        await wait_for_http_response(
            process,
            self.proxy_url,
            lambda response: response.status_code < 500,
        )

        try:
            certificate = self.ca_certificate_path.read_bytes()
        except OSError as error:
            raise RuntimeError(
                f"pywb started without creating its proxy CA at {self.ca_certificate_path}"
            ) from error

        if b"BEGIN CERTIFICATE" not in certificate:
            raise RuntimeError(f"pywb created an invalid proxy CA at {self.ca_certificate_path}")


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
        )

        try:
            process = self.process

            if not process:
                raise RuntimeError("pywb replay process has not started")

            await wait_for_http_response(
                process,
                f"http://{HOST}:{self.port}/",
                lambda response: response.status_code < 500,
            )
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
        )

        result = await wait_for_process(process)

        if result != 0:
            raise RuntimeError("pywb could not reindex the recording collection")


__all__ = [
    "PyWBRecorder",
    "PyWBReplayServer",
]
