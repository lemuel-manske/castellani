from collections.abc import AsyncIterator
from dataclasses import dataclass


@dataclass(frozen=True)
class ArchivePage:
    url: str
    status: str
    snapshot_id: str | None = None
    error_code: str | None = None
    captured_at: str | None = None


@dataclass(frozen=True)
class PageListing:
    items: tuple[ArchivePage, ...]
    next_cursor: str | None = None


@dataclass(frozen=True)
class SnapshotReference:
    archive_id: str
    snapshot_id: str
    url: str
    final_url: str
    captured_at: str
    content_type: str | None = None


@dataclass(frozen=True)
class WACZObject:
    body: AsyncIterator[bytes] | None
    content_length: int
    etag: str
    last_modified: str | None
    content_range: str | None
    partial: bool

    async def consume(self) -> bytes:
        if self.body is None:
            raise RuntimeError("WACZ object has no body")

        return b"".join([chunk async for chunk in self.body])


class InvalidArchiveCursor(ValueError):
    pass


class InvalidPageLimit(ValueError):
    """Raised when a page listing limit is outside the supported range."""


class InvalidWACZRange(ValueError):
    pass


class WACZRangeNotSatisfiable(ValueError):
    def __init__(self, content_length: int) -> None:
        super().__init__("requested range is not satisfiable")
        self.content_length = content_length
