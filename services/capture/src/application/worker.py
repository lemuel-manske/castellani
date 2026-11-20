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

POLL_INTERVAL_SECONDS = 1
WORKER_SHUTDOWN_TIMEOUT_SECONDS = 30


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
        completed = False

        try:
            reservation_id = await self.capacity.reserve(claim.attempt_id)

            if reservation_id is None:
                await self.repository.release(claim)
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
            completed = True
        except asyncio.CancelledError:
            raise
        except Exception as error:
            await self._handle_failure(claim, error)
        finally:
            if directory is not None and not completed:
                await self._discard_attempt(claim, directory)

            if reservation_id is not None:
                await self.capacity.release(claim.attempt_id, reservation_id)

    async def _handle_failure(self, claim: TaskClaim, error: Exception) -> None:
        reason_code = getattr(error, "reason_code", "capture_failed")

        await self.repository.fail(claim, str(reason_code), str(error))
        await self.on_error(error)

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
        receive: Callable[[], Awaitable[tuple[str, str] | None]],
        acknowledge: Callable[[str, str], Awaitable[None]],
        reject: Callable[[str, str], Awaitable[None]],
    ) -> None:
        self.worker = worker
        self.receive = receive
        self.acknowledge = acknowledge
        self.reject = reject
        self._stopping = asyncio.Event()

    def stop(self) -> None:
        self._stopping.set()

    async def run(self) -> None:
        while not self._stopping.is_set():
            delivery = await self.receive()

            if delivery is None:
                await self._wait_for_work()
                continue

            archive_id, url_key = delivery

            try:
                claimed = await self.worker.execute(archive_id, url_key)
            except asyncio.CancelledError:
                raise
            except Exception:
                await self.reject(archive_id, url_key)
                continue

            if claimed:
                await self.acknowledge(archive_id, url_key)
            else:
                await self.acknowledge(archive_id, url_key)

    async def _wait_for_work(self) -> None:
        try:
            await asyncio.wait_for(
                self._stopping.wait(),
                timeout=POLL_INTERVAL_SECONDS,
            )
        except TimeoutError:
            return
