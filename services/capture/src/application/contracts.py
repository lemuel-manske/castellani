from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from domain.task import TaskClaim


@dataclass(frozen=True)
class CaptureArtifact:
    """Metadata and files produced by capturing one page."""

    requested_url: str
    final_url: str
    redirect_chain: tuple[str, ...]
    status_code: int | None
    content_type: str | None
    title: str
    captured_at: str
    discovered_urls: tuple[str, ...]
    blocked_urls: tuple[str, ...]
    warc_files: tuple[Path, ...]


@dataclass(frozen=True)
class CaptureOutcome:
    """A completed capture attempt ready to be committed to task state."""

    archive_id: str
    url_key: str
    attempt_id: str
    fence: int
    artifact: CaptureArtifact


class TaskRepository(Protocol):
    """Owns authoritative task claims and capture-attempt state."""

    async def claim(self, archive_id: str, url_key: str) -> TaskClaim | None: ...

    async def renew(self, claim: TaskClaim) -> TaskClaim: ...

    async def complete(self, outcome: CaptureOutcome) -> None: ...

    async def fail(self, claim: TaskClaim, reason_code: str, message: str) -> None: ...

    async def release(self, claim: TaskClaim) -> None: ...


class BrowserCapacity(Protocol):
    """Controls the number of page captures running concurrently."""

    async def reserve(self, attempt_id: str) -> str | None: ...

    async def release(self, attempt_id: str, reservation_id: str) -> None: ...


class PageExecutor(Protocol):
    """Executes a browser capture and returns its resulting artifacts."""

    async def execute(self, url: str, output_dir: Path) -> CaptureArtifact: ...


class ArtifactStore(Protocol):
    """Manages temporary storage for individual capture attempts."""

    async def create_attempt_directory(self, claim: TaskClaim) -> Path: ...

    async def discard_attempt(self, claim: TaskClaim, directory: Path) -> None: ...


class DiscoveryPublisher(Protocol):
    """Publishes URLs discovered during a page capture."""

    async def publish_discovered(
        self,
        claim: TaskClaim,
        discovered_urls: tuple[str, ...],
    ) -> None: ...
