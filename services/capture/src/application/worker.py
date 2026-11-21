import asyncio
import time
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Protocol

from application.contracts import ArtifactStore, CaptureArtifact, CaptureExecutor
from domain import (
    CaptureAllocator,
    CaptureOutcome,
    CaptureReservation,
    TaskClaim,
    TaskRepository,
)
from utils.fn import awaitable, noop


class LeaseLostError(RuntimeError):
    """Raised when a worker can no longer prove ownership of its execution leases."""


class CaptureWorker(Protocol):
    """A callable that executes a page capture for a claimed task."""

    async def __call__(self, archive_id: str, url_key: str) -> bool: ...


class ConcreteCaptureWorker(CaptureWorker):
    """Coordinates the lifecycle of a claimed page capture."""

    def __init__(
        self,
        repository: TaskRepository,
        alloc: CaptureAllocator,
        executor: CaptureExecutor,
        artifacts: ArtifactStore,
        on_error: Callable[[Exception], Awaitable[None]] | None = None,
    ) -> None:
        self.repository = repository
        self.alloc = alloc
        self.executor = executor
        self.artifacts = artifacts

        self.on_error = on_error or awaitable(noop)

    async def __call__(self, archive_id: str, url_key: str) -> bool:
        claim = await self.repository.claim(archive_id, url_key)

        if claim is None:
            return False

        await self._execute_claim(claim)

        return True

    async def _execute_claim(self, claim: TaskClaim) -> None:
        claim_state = [claim]

        reservation_state: list[CaptureReservation | None] = [None]
        directory_state: list[Path | None] = [None]
        artifact_claim_state: list[TaskClaim | None] = [None]

        terminal_state = [False]

        stop_heartbeat = asyncio.Event()
        lease_changed = asyncio.Event()

        heartbeat = asyncio.create_task(
            self._maintain_leases(
                claim_state,
                reservation_state,
                stop_heartbeat,
                lease_changed,
            )
        )

        operation = asyncio.create_task(
            self._run_claim(
                claim_state,
                reservation_state,
                directory_state,
                artifact_claim_state,
                terminal_state,
                lease_changed,
            )
        )

        try:
            done, _ = await asyncio.wait(
                (operation, heartbeat),
                return_when=asyncio.FIRST_COMPLETED,
            )

            if operation in done:
                stop_heartbeat.set()
                lease_changed.set()
                await heartbeat

                try:
                    await operation
                except Exception as error:
                    await self.repository.fail(
                        claim_state[0],
                        str(getattr(error, "reason_code", "capture_failed")),
                        str(error),
                    )

                    await self.on_error(error)

                return

            heartbeat_error = heartbeat.exception()

            operation.cancel()

            await asyncio.gather(operation, return_exceptions=True)

            if heartbeat_error is not None:
                raise heartbeat_error

            raise LeaseLostError("lease heartbeat stopped unexpectedly")

        except asyncio.CancelledError:
            stop_heartbeat.set()
            lease_changed.set()

            operation.cancel()
            heartbeat.cancel()

            await asyncio.gather(operation, heartbeat, return_exceptions=True)

            raise

        finally:
            stop_heartbeat.set()
            lease_changed.set()

            if not heartbeat.done():
                heartbeat.cancel()

                await asyncio.gather(heartbeat, return_exceptions=True)

            directory = directory_state[0]

            artifact_claim = artifact_claim_state[0]

            if directory is not None and artifact_claim is not None and not terminal_state[0]:
                try:
                    await self.artifacts.discard_attempt(claim, directory)
                except Exception as error:
                    await self.on_error(error)

            reservation = reservation_state[0]

            if reservation is not None:
                try:
                    await self.alloc.release(reservation)
                except Exception as error:
                    await self.on_error(error)

    async def _run_claim(
        self,
        claim_state: list[TaskClaim],
        reservation_state: list[CaptureReservation | None],
        directory_state: list[Path | None],
        artifact_claim_state: list[TaskClaim | None],
        terminal_state: list[bool],
        lease_changed: asyncio.Event,
    ) -> None:
        reservation = await self.alloc.reserve(claim_state[0].attempt_id)

        if reservation is None:
            await self.repository.release(claim_state[0])

            terminal_state[0] = True

            return

        reservation_state[0] = reservation

        lease_changed.set()

        artifact_claim = claim_state[0]

        directory = await self.artifacts.create_attempt_directory(artifact_claim)

        artifact_claim_state[0] = artifact_claim
        directory_state[0] = directory

        artifact: CaptureArtifact = await self.executor.execute(
            claim_state[0].task.url,
            directory,
        )

        await self.repository.admit_discovered(
            claim_state[0],
            artifact.capture.discovered_urls,
        )

        claim = claim_state[0]

        outcome = CaptureOutcome(
            archive_id=claim.task.archive_id,
            url_key=claim.task.url_key,
            attempt_id=claim.attempt_id,
            fence=claim.fence,
            capture=artifact.capture,
        )

        await self.repository.complete(outcome, artifact.warc_files)

        terminal_state[0] = True

    async def _maintain_leases(
        self,
        claim_state: list[TaskClaim],
        reservation_state: list[CaptureReservation | None],
        stop: asyncio.Event,
        lease_changed: asyncio.Event,
    ) -> None:
        while not stop.is_set():
            claim = claim_state[0]
            reservation = reservation_state[0]

            expiries = [claim.lease_until]

            if reservation is not None:
                expiries.append(reservation.lease_until)

            remaining = min(expiries) - time.time()

            if remaining <= 0:
                raise LeaseLostError("an execution lease expired before it could be renewed")

            lease_changed.clear()

            try:
                await asyncio.wait_for(lease_changed.wait(), timeout=remaining / 3)

                if stop.is_set():
                    return

                continue
            except TimeoutError:
                if stop.is_set():
                    return

            claim = claim_state[0]
            reservation = reservation_state[0]

            remaining = (
                min(
                    [claim.lease_until]
                    + ([reservation.lease_until] if reservation is not None else [])
                )
                - time.time()
            )

            if remaining <= 0:
                raise LeaseLostError("an execution lease expired before renewal began")

            try:
                if reservation is None:
                    renewed_claim = await asyncio.wait_for(
                        self.repository.renew(claim),
                        timeout=remaining * 0.8,
                    )

                    claim.verify_renewal(renewed_claim, time.time())

                    claim_state[0] = renewed_claim

                    continue

                renewals = await asyncio.wait_for(
                    asyncio.gather(
                        self.repository.renew(claim),
                        self.alloc.renew(reservation),
                        return_exceptions=True,
                    ),
                    timeout=remaining * 0.8,
                )

                renewed_claim, renewed_reservation = renewals

                if not isinstance(renewed_claim, BaseException):
                    claim.verify_renewal(renewed_claim, time.time())

                    claim_state[0] = renewed_claim

                if not isinstance(renewed_reservation, BaseException):
                    reservation.verify_renewal(renewed_reservation, time.time())

                    reservation_state[0] = renewed_reservation

                if isinstance(renewed_claim, BaseException):
                    raise renewed_claim

                if isinstance(renewed_reservation, BaseException):
                    raise renewed_reservation

            except Exception as error:
                raise LeaseLostError("failed to renew execution ownership") from error
