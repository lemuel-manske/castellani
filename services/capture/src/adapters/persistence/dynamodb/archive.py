import asyncio
import base64
import binascii
import json
from collections.abc import AsyncIterator
from datetime import datetime
from email.utils import format_datetime
from typing import Any, cast

from domain import (
    ArchivePage,
    ArchiveRetrieval,
    InvalidArchiveCursor,
    InvalidWACZRange,
    PageListing,
    SnapshotReference,
    WACZObject,
    WACZRangeNotSatisfiable,
)

from .queries.task import read_run
from .tables import FRONTIER_TABLE, RUNS_TABLE, SNAPSHOTS_TABLE

PAGE_STATUSES = {
    "PENDING": "PENDING",
    "CLAIMED": "RUNNING",
    "WAITING_FOR_AUTH": "WAITING_FOR_AUTH",
    "COMPLETED": "CAPTURED",
    "FAILED": "FAILED",
}

DEFAULT_PAGE_LIMIT = 25

MAX_PAGE_LIMIT = 100

WACZ_READ_CHUNK_BYTES = 64 * 1024


class DynamoDBArchiveRetrieval(ArchiveRetrieval):
    def __init__(
        self,
        client: Any,
        s3_client: Any,
        artifact_bucket: str,
    ) -> None:
        self.client = client
        self.s3_client = s3_client
        self.artifact_bucket = artifact_bucket

    async def list_pages(
        self,
        archive_id: str,
        limit: int,
        cursor: str | None,
    ) -> PageListing:
        if limit < 1 or limit > MAX_PAGE_LIMIT:
            raise ValueError("limit must be between 1 and 100")

        return await asyncio.to_thread(self._list_pages, archive_id, limit, cursor)

    def _list_pages(
        self,
        archive_id: str,
        limit: int,
        cursor: str | None,
    ) -> PageListing:
        request: dict[str, Any] = {
            "TableName": FRONTIER_TABLE,
            "KeyConditionExpression": "archiveId = :archive_id",
            "ExpressionAttributeValues": {":archive_id": {"S": archive_id}},
            "Limit": limit,
        }

        if cursor is not None:
            request["ExclusiveStartKey"] = decode_cursor(cursor, archive_id)

        response = self.client.query(**request)

        items = tuple(page_from_item(item) for item in response.get("Items", ()))

        last_key = response.get("LastEvaluatedKey")

        return PageListing(
            items=items,
            next_cursor=encode_cursor(last_key) if last_key else None,
        )

    async def read_snapshot(
        self,
        archive_id: str,
        snapshot_id: str,
    ) -> SnapshotReference | None:
        return await asyncio.to_thread(self._read_snapshot, archive_id, snapshot_id)

    def _read_snapshot(self, archive_id: str, snapshot_id: str) -> SnapshotReference | None:
        response = self.client.get_item(
            TableName=SNAPSHOTS_TABLE,
            Key={"snapshotId": {"S": snapshot_id}},
            ConsistentRead=True,
        )

        item = response.get("Item")

        if item is None or string_value(item, "archiveId") != archive_id:
            return None

        return SnapshotReference(
            archive_id=archive_id,
            snapshot_id=snapshot_id,
            url=string_value(item, "url"),
            final_url=string_value(item, "finalUrl", default=""),
            captured_at=string_value(item, "capturedAt"),
            content_type=string_value(item, "contentType") or None,
        )

    async def read_wacz(
        self,
        archive_id: str,
        range_header: str | None,
        if_range: str | None,
        metadata_only: bool = False,
    ) -> WACZObject | None:
        return await asyncio.to_thread(
            self._read_wacz,
            archive_id,
            range_header,
            if_range,
            metadata_only,
        )

    def _read_wacz(
        self,
        archive_id: str,
        range_header: str | None,
        if_range: str | None,
        metadata_only: bool,
    ) -> WACZObject | None:
        run = read_run(self.client, RUNS_TABLE, archive_id)

        if run is None or string_value(run, "decision", default="") != "PUBLISH":
            return None

        if string_value(run, "replayStatus", default="") != "READY":
            return None

        key = string_value(run, "packageKey", default="")

        if not key:
            return None

        bucket = string_value(run, "packageBucket", default="") or self.artifact_bucket

        head = self.s3_client.head_object(Bucket=bucket, Key=key)

        etag = str(head["ETag"])
        content_length = int(head["ContentLength"])

        last_modified = head.get("LastModified")

        if_range_matches = if_range is None or normalize_etag(if_range) == normalize_etag(etag)

        requested = (
            parse_range(range_header, content_length) if range_header and if_range_matches else None
        )

        if requested is None:
            body = (
                None if metadata_only else self.s3_client.get_object(Bucket=bucket, Key=key)["Body"]
            )

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
                Bucket=bucket,
                Key=key,
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


def page_from_item(item: dict[str, Any]) -> ArchivePage:
    state = string_value(item, "state")

    try:
        status = PAGE_STATUSES[state]
    except KeyError as error:
        raise RuntimeError(f"unknown page state: {state}") from error

    return ArchivePage(
        url=string_value(item, "url"),
        status=status,
        snapshot_id=string_value(item, "snapshotId", default="") or None,
        error_code=string_value(item, "failureReason", default="") or None,
        captured_at=string_value(item, "capturedAt", default="") or None,
    )


def string_value(item: dict[str, Any], key: str, default: str | None = None) -> str:
    value = item.get(key, {}).get("S")

    if isinstance(value, str):
        return value

    if default is not None:
        return default

    raise RuntimeError(f"DynamoDB item has an invalid {key}")


def encode_cursor(key: dict[str, Any]) -> str:
    data = json.dumps(key, sort_keys=True, separators=(",", ":")).encode()

    return base64.urlsafe_b64encode(data).decode().rstrip("=")


def decode_cursor(cursor: str, archive_id: str) -> dict[str, Any]:
    try:
        padding = "=" * (-len(cursor) % 4)
        data = base64.urlsafe_b64decode(cursor + padding)
        key: Any = json.loads(data)
    except (binascii.Error, UnicodeDecodeError, json.JSONDecodeError, ValueError) as error:
        raise InvalidArchiveCursor from error

    if not isinstance(key, dict):
        raise InvalidArchiveCursor

    typed_key = cast(dict[str, Any], key)

    if typed_key.get("archiveId", {}).get("S") != archive_id:
        raise InvalidArchiveCursor

    if not isinstance(typed_key.get("urlKey", {}).get("S"), str):
        raise InvalidArchiveCursor

    return typed_key


def http_last_modified(value: datetime | None) -> str | None:
    if value is None:
        return None

    return format_datetime(value, usegmt=True)


def normalize_etag(value: str) -> str:
    return value.removeprefix("W/").strip('"')


def parse_range(header: str, content_length: int) -> tuple[int, int | None]:
    if not header.startswith("bytes=") or "," in header:
        raise InvalidWACZRange

    try:
        start_text, end_text = header[6:].split("-", 1)

        if not start_text:
            suffix_length = int(end_text)

            if suffix_length < 1:
                raise InvalidWACZRange

            return max(0, content_length - suffix_length), content_length - 1

        start = int(start_text)
        end = int(end_text) if end_text else None
    except ValueError as error:
        raise InvalidWACZRange from error

    if start < 0 or (end is not None and end < start):
        raise InvalidWACZRange

    return start, end


async def stream_body(body: Any) -> AsyncIterator[bytes]:
    try:
        while chunk := await asyncio.to_thread(body.read, WACZ_READ_CHUNK_BYTES):
            yield chunk
    finally:
        await asyncio.to_thread(body.close)
