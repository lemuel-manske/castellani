import asyncio
import time
from dataclasses import replace
from pathlib import Path

from application.contracts import BrowserReservation, CaptureArtifact, CaptureOutcome
from domain.task import TaskClaim


class FakeRepository:
    def __init__(self, claim: TaskClaim) -> None:
        self.claim_result = claim
        self.failed: tuple[TaskClaim, str, str] | None = None
        self.completed: CaptureOutcome | None = None
        self.renewals = 0

    async def claim(self, archive_id: str, url_key: str) -> TaskClaim | None:
        return self.claim_result

    async def renew(self, claim: TaskClaim) -> TaskClaim:
        self.renewals += 1
        return replace(claim, lease_until=time.time() + 60)

    async def complete(self, outcome: CaptureOutcome) -> None:
        self.completed = outcome

    async def fail(self, claim: TaskClaim, reason_code: str, message: str) -> None:
        self.failed = (claim, reason_code, message)

    async def release(self, claim: TaskClaim) -> None:
        return None

    async def admit_discovered(
        self,
        claim: TaskClaim,
        discovered_urls: tuple[str, ...],
    ) -> None:
        return None


class FakeCapacity:
    async def reserve(self, attempt_id: str) -> BrowserReservation | None:
        return BrowserReservation(
            attempt_id=attempt_id,
            reservation_id="reservation-1",
            slot_id="slot-1",
            fence=1,
            lease_until=time.time() + 60,
        )

    async def renew(self, reservation: BrowserReservation) -> BrowserReservation:
        return replace(reservation, lease_until=time.time() + 60)

    async def release(self, reservation: BrowserReservation) -> None:
        return None


class FailingPageExecutor:
    async def execute(self, url: str, output_dir: Path) -> CaptureArtifact:
        raise RuntimeError("browser capture failed")


class FakeArtifactStore:
    def __init__(self, directory: Path) -> None:
        self.directory = directory
        self.discarded: list[tuple[TaskClaim, Path]] = []

    async def create_attempt_directory(self, claim: TaskClaim) -> Path:
        return self.directory

    async def discard_attempt(self, claim: TaskClaim, directory: Path) -> None:
        self.discarded.append((claim, directory))


class SlowPageExecutor:
    async def execute(self, url: str, output_dir: Path) -> CaptureArtifact:
        await asyncio.sleep(0.4)
        return CaptureArtifact(
            requested_url=url,
            final_url=url,
            redirect_chain=(),
            status_code=200,
            content_type="text/html",
            title="Example",
            captured_at="2026-11-20T12:00:00Z",
            discovered_urls=(),
            blocked_urls=(),
            warc_files=(),
        )


class ShortLeaseRepository(FakeRepository):
    async def renew(self, claim: TaskClaim) -> TaskClaim:
        self.renewals += 1
        return replace(claim, lease_until=time.time() + 0.3)


class ShortLeaseCapacity(FakeCapacity):
    def __init__(self) -> None:
        self.renewals = 0

    async def reserve(self, attempt_id: str) -> BrowserReservation:
        return BrowserReservation(
            attempt_id=attempt_id,
            reservation_id="reservation-1",
            slot_id="slot-1",
            fence=1,
            lease_until=time.time() + 0.06,
        )

    async def renew(self, reservation: BrowserReservation) -> BrowserReservation:
        self.renewals += 1
        return replace(reservation, lease_until=time.time() + 0.06)


class ExpiringRepository(FakeRepository):
    async def renew(self, claim: TaskClaim) -> TaskClaim:
        raise RuntimeError("DynamoDB unavailable")


class BlockingPageExecutor:
    def __init__(self) -> None:
        self.started = asyncio.Event()
        self.cancelled = asyncio.Event()

    async def execute(self, url: str, output_dir: Path) -> CaptureArtifact:
        self.started.set()

        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            self.cancelled.set()
            raise


class ExpiringCapacity(FakeCapacity):
    async def renew(self, reservation: BrowserReservation) -> BrowserReservation:
        raise RuntimeError("capacity store unavailable")
