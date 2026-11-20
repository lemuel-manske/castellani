import asyncio
from collections.abc import Awaitable, Callable
from pathlib import Path

from application.contracts import (
    ArtifactStore,
    BrowserCapacity,
    CaptureOutcome,
    DiscoveryPublisher,
    PageExecutor,
    PageTaskConsumer,
    PageTaskProcessor,
    TaskRepository,
)
from domain.task import TaskClaim

WORKER_POLL_INTERVAL_SECONDS = 1


class Worker:
    """Coordinates the lifecycle of a claimed page capture."""

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

    async def _discard_attempt(self, claim: TaskClaim, directory: Path) -> None:
        try:
            await self.artifacts.discard_attempt(claim, directory)
        except Exception as error:
            await self.on_error(error)

    @staticmethod
    async def _ignore_error(error: Exception) -> None:
        return None


class WorkerRuntime:
    """Runs the capture worker as a consumer of page-task messages."""

    def __init__(
        self,
        worker: PageTaskProcessor,
        consumer: PageTaskConsumer,
    ) -> None:
        self.worker = worker
        self.consumer = consumer
        self._stopping = asyncio.Event()

    def stop(self) -> None:
        self._stopping.set()

    async def run(self) -> None:
        while not self._stopping.is_set():
            message = await self.consumer.receive()

            if message is None:
                await self._wait_for_work()
                continue

            try:
                delivery = message.delivery
                await self.worker.execute(delivery.archive_id, delivery.url_key)
            except asyncio.CancelledError:
                raise
            except Exception:
                await message.reject()
                continue

            await message.acknowledge()

    async def _wait_for_work(self) -> None:
        try:
            await asyncio.wait_for(
                self._stopping.wait(),
                timeout=WORKER_POLL_INTERVAL_SECONDS,
            )
        except TimeoutError:
            return
