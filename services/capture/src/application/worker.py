import asyncio
from collections.abc import Awaitable, Callable
from pathlib import Path

from application.contracts import (
    ArtifactStore,
    BrowserCapacity,
    CaptureOutcome,
    PageExecutor,
    TaskRepository,
)
from domain.task import TaskClaim


class Worker:
    """Coordinates the lifecycle of a claimed page capture."""

    def __init__(
        self,
        repository: TaskRepository,
        capacity: BrowserCapacity,
        executor: PageExecutor,
        artifacts: ArtifactStore,
        on_error: Callable[[Exception], Awaitable[None]] | None = None,
    ) -> None:
        self.repository = repository
        self.capacity = capacity
        self.executor = executor
        self.artifacts = artifacts

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

            await self.repository.admit_discovered(claim, artifact.discovered_urls)

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
