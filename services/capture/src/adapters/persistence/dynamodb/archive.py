import asyncio
from typing import Any

from domain.capture import (
    InvalidPageLimit,
    PageListing,
    SnapshotReference,
    WACZObject,
    WACZRangeNotSatisfiable,
)
from ports.capture import ArchiveRetrieval
from topology.buckets import ARCHIVE_ARTIFACTS_BUCKET
from utils.http import http_last_modified, normalize_etag, parse_range
from utils.io import stream_body

from .queries.archive import MAX_PAGE_LIMIT, query_pages
from .queries.archive import read_snapshot as read_snapshot_query
from .queries.task import read_run
from .values import optional_string


class DynamoDBArchiveRetrieval(ArchiveRetrieval):
    def __init__(
        self,
        client: Any,
        s3_client: Any,
    ) -> None:
        self.client = client
        self.s3_client = s3_client

    async def list_pages(
        self,
        archive_id: str,
        limit: int,
        cursor: str | None,
    ) -> PageListing:
        if limit < 1 or limit > MAX_PAGE_LIMIT:
            raise InvalidPageLimit("limit must be between 1 and 100")

        def read() -> PageListing:
            return query_pages(self.client, archive_id, limit, cursor)

        return await asyncio.to_thread(read)

    async def read_snapshot(
        self,
        archive_id: str,
        snapshot_id: str,
    ) -> SnapshotReference | None:
        def read() -> SnapshotReference | None:
            return read_snapshot_query(self.client, archive_id, snapshot_id)

        return await asyncio.to_thread(read)

    async def read_wacz(
        self,
        archive_id: str,
        range_header: str | None,
        if_range: str | None,
        metadata_only: bool = False,
    ) -> WACZObject | None:
        def read() -> WACZObject | None:
            run = read_run(self.client, archive_id)

            if run is None or (optional_string(run, "decision") or "") != "PUBLISH":
                return None

            if (optional_string(run, "replayStatus") or "") != "READY":
                return None

            key = optional_string(run, "packageKey") or ""

            if not key:
                return None

            bucket = optional_string(run, "packageBucket") or ARCHIVE_ARTIFACTS_BUCKET
            request: dict[str, Any] = {"Bucket": bucket, "Key": key}

            head = self.s3_client.head_object(**request)

            etag = str(head["ETag"])
            content_length = int(head["ContentLength"])

            last_modified = head.get("LastModified")

            if_range_matches = if_range is None or normalize_etag(if_range) == normalize_etag(etag)

            requested = (
                parse_range(range_header, content_length)
                if range_header and if_range_matches
                else None
            )

            if requested is None:
                body = None if metadata_only else self.s3_client.get_object(**request)["Body"]

                return WACZObject(
                    body=None if body is None else stream_body(body),
                    content_length=content_length,
                    etag=etag,
                    last_modified=http_last_modified(last_modified),
                    content_range=None,
                    partial=False,
                )

            start, end = requested

            if start >= content_length or start < 0:
                raise WACZRangeNotSatisfiable(content_length)

            end = min(end, content_length - 1) if end is not None else content_length - 1

            body = None

            if not metadata_only:
                body = self.s3_client.get_object(
                    **request,
                    Range=f"bytes={start}-{end}",
                )["Body"]

            return WACZObject(
                body=None if body is None else stream_body(body),
                content_length=end - start + 1,
                etag=etag,
                last_modified=http_last_modified(last_modified),
                content_range=f"bytes {start}-{end}/{content_length}",
                partial=True,
            )

        return await asyncio.to_thread(read)
