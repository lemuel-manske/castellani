import asyncio
import json
import signal
import socket
from pathlib import Path
from typing import Self

import httpx

COLLECTION_NAME = "capture"
CA_DOWNLOAD_PATH = "/wsgiprox/download/pem"
STARTUP_TIMEOUT_SECONDS = 15
PROCESS_SHUTDOWN_TIMEOUT_SECONDS = 10


class PyWBRecorder:
    def __init__(self, output_dir: Path) -> None:
        self.output_dir = output_dir
        self.collections_dir = output_dir / "collections"
        self.ca_certificate_path = output_dir / "proxy-certs" / "pywb-ca.pem"
        self.port = self._available_port()
        self.process: asyncio.subprocess.Process | None = None

    @property
    def proxy_url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    @property
    def warc_files(self) -> tuple[Path, ...]:
        archive_dir = self.collections_dir / COLLECTION_NAME / "archive"
        return tuple(sorted(archive_dir.glob("*.warc.gz")))

    async def start(self) -> Self:
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
        if self.process is None or self.process.returncode is not None:
            return

        self.process.send_signal(signal.SIGINT)

        try:
            await asyncio.wait_for(
                self.process.wait(),
                timeout=PROCESS_SHUTDOWN_TIMEOUT_SECONDS,
            )
        except TimeoutError:
            self.process.kill()
            await self.process.wait()

    def _write_config(self) -> None:
        config = f"""collections_root: {json.dumps(str(self.collections_dir))}
archive_paths:
  - archive
index_paths:
  - indexes
collections:
  live: "$live"
proxy:
  coll: {COLLECTION_NAME}
  recording: true
  ca_file_cache: {json.dumps(str(self.ca_certificate_path))}
  enable_content_rewrite: false
recorder:
  source_coll: live
  filename_template: "capture-{{timestamp}}-{{hostname}}-{{random}}.warc.gz"
"""
        config_path = self.output_dir / "config.yaml"
        config_path.write_text(config, encoding="utf-8")

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
        deadline = asyncio.get_running_loop().time() + STARTUP_TIMEOUT_SECONDS

        async with httpx.AsyncClient(trust_env=False, timeout=1) as client:
            while asyncio.get_running_loop().time() < deadline:
                if self.process is None or self.process.returncode is not None:
                    raise RuntimeError("pywb recorder exited before becoming ready")

                try:
                    response = await client.get(f"{self.proxy_url}{CA_DOWNLOAD_PATH}")
                except httpx.TransportError:
                    await asyncio.sleep(0.1)
                    continue

                if response.status_code == 200 and b"BEGIN CERTIFICATE" in response.content:
                    self.ca_certificate_path.write_bytes(response.content)
                    return

                await asyncio.sleep(0.1)

        raise TimeoutError("pywb recorder did not become ready in time")

    @staticmethod
    def _available_port() -> int:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
            listener.bind(("127.0.0.1", 0))
            return int(listener.getsockname()[1])
