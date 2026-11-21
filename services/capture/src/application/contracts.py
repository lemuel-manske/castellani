from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from domain.browser_reservation import BrowserReservation
from domain.capture import CaptureOutcome, PageCapture
from domain.task import TaskClaim


@dataclass(frozen=True)
class CaptureArtifact:
    """Browser execution output and its attempt-local WARC files."""

    capture: PageCapture
    blocked_urls: tuple[str, ...]
    warc_files: tuple[Path, ...]


class TaskRepository(Protocol):
    """Owns authoritative task claims and capture-attempt state."""

    async def claim(self, archive_id: str, url_key: str) -> TaskClaim | None: ...

    async def renew(self, claim: TaskClaim) -> TaskClaim: ...

    async def complete(
        self,
        outcome: CaptureOutcome,
        warc_files: tuple[Path, ...],
    ) -> None: ...

    async def fail(self, claim: TaskClaim, reason_code: str, message: str) -> None: ...

    async def release(self, claim: TaskClaim) -> None: ...

    async def admit_discovered(
        self,
        claim: TaskClaim,
        discovered_urls: tuple[str, ...],
    ) -> None:
        """Durably account for discoveries before allowing parent completion."""
        ...


class BrowserCapacity(Protocol):
    """Controls the number of page captures running concurrently."""

    async def reserve(self, attempt_id: str) -> BrowserReservation | None: ...

    async def renew(self, reservation: BrowserReservation) -> BrowserReservation: ...

    async def release(self, reservation: BrowserReservation) -> None: ...


class PageExecutor(Protocol):
    """
    Executes a browser capture and returns its resulting artifacts.

    Implementations must stop underlying browser work when execution is cancelled.
    """

    async def execute(self, url: str, output_dir: Path) -> CaptureArtifact: ...


class ArtifactStore(Protocol):
    """Manages temporary storage for individual capture attempts."""

    async def create_attempt_directory(self, claim: TaskClaim) -> Path: ...

    async def discard_attempt(self, claim: TaskClaim, directory: Path) -> None: ...
