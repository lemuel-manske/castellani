import asyncio
import time
from collections.abc import Awaitable, Callable
from pathlib import Path

from application.contracts import (
    ArtifactStore,
    BrowserCapacity,
    CaptureArtifact,
    PageExecutor,
    TaskRepository,
)
from domain.browser_reservation import BrowserReservation
from domain.capture import CaptureOutcome
from domain.task import TaskClaim
from utils.fn import awaitable, noop


class LeaseLostError(RuntimeError):
    """Raised when a worker can no longer prove ownership of its execution leases."""


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

        self.on_error = on_error or awaitable(noop)

    async def execute(self, archive_id: str, url_key: str) -> bool:
        claim = await self.repository.claim(archive_id, url_key)

        if claim is None:
            return False

        await self._execute_claim(claim)

        return True

    async def _execute_claim(self, claim: TaskClaim) -> None:
        claim_state = [claim]
        reservation_state: list[BrowserReservation | None] = [None]
        directory_state: list[Path | None] = [None]
        terminal_state = [False]
        stop_heartbeat = asyncio.Event()

        heartbeat = asyncio.create_task(
            self._maintain_leases(claim_state, reservation_state, stop_heartbeat)
        )
        operation = asyncio.create_task(
            self._run_claim(
                claim_state,
                reservation_state,
                directory_state,
                terminal_state,
            )
        )

        try:
            done, _ = await asyncio.wait(
                (operation, heartbeat),
                return_when=asyncio.FIRST_COMPLETED,
            )

            if operation in done:
                stop_heartbeat.set()
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
            operation.cancel()
            heartbeat.cancel()
            await asyncio.gather(operation, heartbeat, return_exceptions=True)
            raise

        finally:
            stop_heartbeat.set()

            if not heartbeat.done():
                heartbeat.cancel()
                await asyncio.gather(heartbeat, return_exceptions=True)

            directory = directory_state[0]

            if directory is not None and not terminal_state[0]:
                await self._discard_attempt(claim_state[0], directory)

            reservation = reservation_state[0]

            if reservation is not None:
                try:
                    await self.capacity.release(reservation)
                except Exception as error:
                    await self.on_error(error)

    async def _run_claim(
        self,
        claim_state: list[TaskClaim],
        reservation_state: list[BrowserReservation | None],
        directory_state: list[Path | None],
        terminal_state: list[bool],
    ) -> None:
        reservation = await self.capacity.reserve(claim_state[0].attempt_id)

        if reservation is None:
            await self.repository.release(claim_state[0])
            terminal_state[0] = True
            return

        reservation_state[0] = reservation

        directory = await self.artifacts.create_attempt_directory(claim_state[0])
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
        reservation_state: list[BrowserReservation | None],
        stop: asyncio.Event,
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

            try:
                await asyncio.wait_for(stop.wait(), timeout=remaining / 3)
                return
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
                        self.capacity.renew(reservation),
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

    async def _discard_attempt(self, claim: TaskClaim, directory: Path) -> None:
        try:
            await self.artifacts.discard_attempt(claim, directory)
        except Exception as error:
            await self.on_error(error)
