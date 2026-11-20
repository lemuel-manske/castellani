from dataclasses import dataclass
from datetime import datetime


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
class CaptureOutcome:
    """A successful page capture tied to the fenced task attempt that produced it."""

    archive_id: str
    url_key: str
    attempt_id: str
    fence: int
    capture: PageCapture

    def __post_init__(self) -> None:
        if not self.archive_id:
            raise ValueError("archive_id must not be empty")

        if not self.url_key:
            raise ValueError("url_key must not be empty")

        if not self.attempt_id:
            raise ValueError("attempt_id must not be empty")

        if self.fence < 1:
            raise ValueError("fence must be positive")
