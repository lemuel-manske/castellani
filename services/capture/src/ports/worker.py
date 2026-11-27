from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path

from domain.capture import ArtifactReference, PageCapture, TaskClaim


class LeaseLostError(RuntimeError):
    """Raised when a worker can no longer prove ownership of its execution leases."""


class CaptureRunner(ABC):
    @abstractmethod
    async def __call__(self, archive_id: str, url_key: str) -> bool: ...


@dataclass(frozen=True)
class CaptureArtifact:
    """Browser execution output and its attempt-local WARC files."""

    capture: PageCapture
    blocked_urls: tuple[str, ...]
    warc_files: tuple[Path, ...]


class ArtifactStore(ABC):
    @abstractmethod
    async def create_attempt_directory(self, claim: TaskClaim) -> Path: ...

    @abstractmethod
    async def persist_attempt(
        self,
        claim: TaskClaim,
        directory: Path,
        snapshot_id: str,
        warc_files: tuple[Path, ...],
    ) -> tuple[ArtifactReference, ...]: ...

    @abstractmethod
    async def discard_attempt(self, claim: TaskClaim, directory: Path) -> None: ...

    @abstractmethod
    async def commit_attempt(self, claim: TaskClaim, directory: Path) -> None: ...
