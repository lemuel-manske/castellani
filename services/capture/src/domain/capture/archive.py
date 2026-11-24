from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Protocol


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


class InvalidArchiveCursor(ValueError):
    pass


class InvalidWACZRange(ValueError):
    pass


class WACZRangeNotSatisfiable(ValueError):
    def __init__(self, content_length: int) -> None:
        super().__init__("requested range is not satisfiable")
        self.content_length = content_length


class ArchiveRetrieval(Protocol):
    async def list_pages(
        self,
        archive_id: str,
        limit: int,
        cursor: str | None,
    ) -> PageListing: ...

    async def read_snapshot(
        self,
        archive_id: str,
        snapshot_id: str,
    ) -> SnapshotReference | None: ...

    async def read_wacz(
        self,
        archive_id: str,
        range_header: str | None,
        if_range: str | None,
        metadata_only: bool = False,
    ) -> WACZObject | None: ...
