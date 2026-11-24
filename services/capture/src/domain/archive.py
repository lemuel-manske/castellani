from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any, Protocol


@dataclass(frozen=True)
class ArchivePage:
    url: str
    status: str
    snapshot_id: str | None = None
    error_code: str | None = None
    captured_at: str | None = None

    def as_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {"url": self.url, "status": self.status}

        if self.snapshot_id is not None:
            result["snapshotId"] = self.snapshot_id

        if self.error_code is not None:
            result["errorCode"] = self.error_code

        if self.captured_at is not None:
            result["capturedAt"] = self.captured_at

        return result


@dataclass(frozen=True)
class PageListing:
    items: tuple[ArchivePage, ...]
    next_cursor: str | None = None

    def as_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "items": [item.as_dict() for item in self.items],
        }

        if self.next_cursor is not None:
            result["nextCursor"] = self.next_cursor

        return result


@dataclass(frozen=True)
class SnapshotReference:
    archive_id: str
    snapshot_id: str
    url: str
    final_url: str
    captured_at: str
    content_type: str | None = None

    def as_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "archiveId": self.archive_id,
            "snapshotId": self.snapshot_id,
            "url": self.url,
            "capturedAt": self.captured_at,
        }

        if self.final_url:
            result["finalUrl"] = self.final_url

        if self.content_type is not None:
            result["contentType"] = self.content_type

        return result


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
