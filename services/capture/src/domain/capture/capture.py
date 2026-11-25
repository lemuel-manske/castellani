from dataclasses import dataclass
from datetime import datetime
from uuid import uuid4

from .auth import DEFAULT_AUTH_GENERATION


@dataclass(frozen=True)
class PageCapture:
    """The domain-relevant facts and discoveries from capturing one page."""

    requested_url: str
    final_url: str
    redirect_chain: tuple[str, ...]
    status_code: int | None
    content_type: str | None
    title: str
    captured_at: datetime
    discovered_urls: tuple[str, ...]

    def __post_init__(self) -> None:
        if not self.requested_url:
            raise ValueError("requested_url must not be empty")

        if not self.final_url:
            raise ValueError("final_url must not be empty")


@dataclass(frozen=True)
class ArtifactReference:
    """Immutable reference to a persisted capture artifact."""

    bucket: str
    key: str
    sha256: str
    size_bytes: int
    version_id: str | None = None

    def __post_init__(self) -> None:
        if not self.bucket or not self.key:
            raise ValueError("artifact bucket and key must not be empty")
        if len(self.sha256) != 64 or any(char not in "0123456789abcdef" for char in self.sha256):
            raise ValueError("artifact sha256 must be a lowercase hexadecimal digest")
        if self.size_bytes < 0:
            raise ValueError("artifact size_bytes must not be negative")


def new_snapshot_id() -> str:
    """Create the immutable identity of one successfully captured page snapshot."""
    return str(uuid4())


@dataclass(frozen=True)
class CaptureOutcome:
    """A successful page capture tied to the fenced task attempt that produced it."""

    archive_id: str
    url_key: str
    attempt_id: str
    fence: int
    snapshot_id: str
    capture: PageCapture
    warc_artifacts: tuple[ArtifactReference, ...]
    auth_generation: int = DEFAULT_AUTH_GENERATION

    def __post_init__(self) -> None:
        if not self.archive_id:
            raise ValueError("archive_id must not be empty")

        if not self.url_key:
            raise ValueError("url_key must not be empty")

        if not self.attempt_id:
            raise ValueError("attempt_id must not be empty")

        if self.fence < 1:
            raise ValueError("fence must be positive")

        if not self.snapshot_id:
            raise ValueError("snapshot_id must not be empty")

        if self.auth_generation < 0:
            raise ValueError("auth generation must not be negative")

        if not self.warc_artifacts:
            raise ValueError("a successful capture must contain at least one WARC artifact")
