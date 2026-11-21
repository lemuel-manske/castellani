from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from domain import PageCapture, TaskClaim


@dataclass(frozen=True)
class CaptureArtifact:
    """Browser execution output and its attempt-local WARC files."""

    capture: PageCapture
    blocked_urls: tuple[str, ...]
    warc_files: tuple[Path, ...]


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
