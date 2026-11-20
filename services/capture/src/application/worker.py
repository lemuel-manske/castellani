import asyncio
from collections.abc import Awaitable, Callable
from pathlib import Path

from application.contracts import (
    ArtifactStore,
    BrowserCapacity,
    CaptureOutcome,
    DiscoveryPublisher,
    PageExecutor,
    TaskRepository,
)
from domain.task import TaskClaim

WORKER_POLL_INTERVAL_SECONDS = 1


class Worker:
    def __init__(
        self,
        repository: TaskRepository,
        capacity: BrowserCapacity,
        executor: PageExecutor,
        artifacts: ArtifactStore,
        discovery: DiscoveryPublisher,
        on_error: Callable[[Exception], Awaitable[None]] | None = None,
    ) -> None:
        self.repository = repository
        self.capacity = capacity
        self.executor = executor
        self.artifacts = artifacts
        self.discovery = discovery
        self.on_error = on_error or self._ignore_error

    async def execute(self, archive_id: str, url_key: str) -> bool:
        claim = await self.repository.claim(archive_id, url_key)

        if claim is None:
            return False

        await self._execute_claim(claim)

        return True

    async def _execute_claim(self, claim: TaskClaim) -> None:
        reservation_id: str | None = None
        directory: Path | None = None
        terminal = False

        try:
            reservation_id = await self.capacity.reserve(claim.attempt_id)

            if reservation_id is None:
                await self.repository.release(claim)
                terminal = True
                return

            directory = await self.artifacts.create_attempt_directory(claim)
            artifact = await self.executor.execute(claim.task.url, directory)

            await self.discovery.publish_discovered(claim, artifact.discovered_urls)

            outcome = CaptureOutcome(
                archive_id=claim.task.archive_id,
                url_key=claim.task.url_key,
                attempt_id=claim.attempt_id,
                fence=claim.fence,
                artifact=artifact,
            )

            await self.repository.complete(outcome)
            terminal = True
        except asyncio.CancelledError:
            raise
        except Exception as error:
            await self.repository.fail(
                claim,
                str(getattr(error, "reason_code", "capture_failed")),
                str(error),
            )
            terminal = True
            await self.on_error(error)
        finally:
            if directory is not None and not terminal:
                await self._discard_attempt(claim, directory)

            if reservation_id is not None:
                await self.capacity.release(claim.attempt_id, reservation_id)

            if directory is not None and not terminal:
                await self._discard_attempt(claim, directory)

    async def _discard_attempt(self, claim: TaskClaim, directory: Path) -> None:
        try:
            await self.artifacts.discard_attempt(claim, directory)
        except Exception as error:
            await self.on_error(error)

    @staticmethod
    async def _ignore_error(error: Exception) -> None:
        return None


class WorkerRuntime:
    def __init__(
        self,
        worker: Worker,
        receive: Callable[[], Awaitable[object | None]],
        acknowledge: Callable[[object], Awaitable[None]],
        reject: Callable[[object], Awaitable[None]],
        delivery_parser: Callable[[object], tuple[str, str]],
    ) -> None:
        self.worker = worker
        self.receive = receive
        self.acknowledge = acknowledge
        self.reject = reject
        self.delivery_parser = delivery_parser
        self._stopping = asyncio.Event()

    def stop(self) -> None:
        self._stopping.set()

    async def run(self) -> None:
        while not self._stopping.is_set():
            delivery = await self.receive()

            if delivery is None:
                await self._wait_for_work()
                continue

            try:
                archive_id, url_key = self.delivery_parser(delivery)
                await self.worker.execute(archive_id, url_key)
            except asyncio.CancelledError:
                raise
            except Exception:
                await self.reject(delivery)
                continue

            await self.acknowledge(delivery)

    async def _wait_for_work(self) -> None:
        try:
            await asyncio.wait_for(
                self._stopping.wait(),
                timeout=WORKER_POLL_INTERVAL_SECONDS,
            )
        except TimeoutError:
            return
