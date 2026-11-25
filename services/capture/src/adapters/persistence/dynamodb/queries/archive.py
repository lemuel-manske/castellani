import base64
import binascii
import json
from typing import Any, cast

from domain.capture import (
    ArchivePage,
    InvalidArchiveCursor,
    PageListing,
    SnapshotReference,
)
from topology.tables import FRONTIER_TABLE, SNAPSHOTS_TABLE

from ..values import optional_string, string_from_item

PAGE_STATUSES = {
    "PENDING": "PENDING",
    "CLAIMED": "RUNNING",
    "WAITING_FOR_AUTH": "WAITING_FOR_AUTH",
    "COMPLETED": "CAPTURED",
    "FAILED": "FAILED",
}

MAX_PAGE_LIMIT = 100


def query_pages(
    client: Any,
    archive_id: str,
    limit: int,
    cursor: str | None,
) -> PageListing:
    request: dict[str, Any] = {
        "TableName": FRONTIER_TABLE,
        "KeyConditionExpression": "archiveId = :archive_id",
        "ExpressionAttributeValues": {":archive_id": {"S": archive_id}},
        "Limit": limit + 1,
    }

    if cursor is not None:
        request["ExclusiveStartKey"] = decode_cursor(cursor, archive_id)

    response = client.query(**request)

    rows = tuple(response.get("Items", ()))
    items = tuple(page_from_item(item) for item in rows[:limit])

    next_cursor = None

    if len(rows) > limit:
        last_item = rows[limit - 1]
        next_cursor = encode_cursor(
            {
                "archiveId": last_item["archiveId"],
                "urlKey": last_item["urlKey"],
            }
        )

    return PageListing(items=items, next_cursor=next_cursor)


def read_snapshot(
    client: Any,
    archive_id: str,
    snapshot_id: str,
) -> SnapshotReference | None:
    response = client.get_item(
        TableName=SNAPSHOTS_TABLE,
        Key={"snapshotId": {"S": snapshot_id}},
        ConsistentRead=True,
    )

    item = response.get("Item")

    if item is None or string_from_item(item, "archiveId", "snapshot") != archive_id:
        return None

    return SnapshotReference(
        archive_id=archive_id,
        snapshot_id=snapshot_id,
        url=string_from_item(item, "url", "snapshot"),
        final_url=optional_string(item, "finalUrl") or "",
        captured_at=string_from_item(item, "capturedAt", "snapshot"),
        content_type=optional_string(item, "contentType") or None,
    )


def page_from_item(item: dict[str, Any]) -> ArchivePage:
    state = string_from_item(item, "state", "frontier page")

    try:
        status = PAGE_STATUSES[state]
    except KeyError as error:
        raise RuntimeError(f"unknown page state: {state}") from error

    return ArchivePage(
        url=string_from_item(item, "url", "frontier page"),
        status=status,
        snapshot_id=optional_string(item, "snapshotId") or None,
        error_code=optional_string(item, "failureReason") or None,
        captured_at=optional_string(item, "capturedAt") or None,
    )


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
