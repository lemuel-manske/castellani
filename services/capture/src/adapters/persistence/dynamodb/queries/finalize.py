from typing import Any

from domain.capture import (
    DEFAULT_NORMALIZER_VERSION,
    MANIFEST_SCHEMA_VERSION,
    ArtifactReference,
    identify_url,
)
from topology.tables import FRONTIER_TABLE, SNAPSHOTS_TABLE

from ..values import deserialize_attribute, optional_string, string_from_item

_SNAPSHOT_INDEX = "archiveId-capturedAt-index"
_PAGE_SIZE = 100


def query_snapshots(client: Any, archive_id: str) -> list[dict[str, Any]]:
    return query_by_archive(
        client,
        SNAPSHOTS_TABLE,
        archive_id,
        index=_SNAPSHOT_INDEX,
    )


def query_frontier(client: Any, archive_id: str) -> list[dict[str, Any]]:
    return query_by_archive(client, FRONTIER_TABLE, archive_id)


def query_by_archive(
    client: Any,
    table: str,
    archive_id: str,
    index: str | None = None,
) -> list[dict[str, Any]]:
    request: dict[str, Any] = {
        "TableName": table,
        "KeyConditionExpression": "#archive_id = :archive_id",
        "ExpressionAttributeNames": {"#archive_id": "archiveId"},
        "ExpressionAttributeValues": {":archive_id": {"S": archive_id}},
        "Limit": _PAGE_SIZE,
    }

    if index is not None:
        request["IndexName"] = index
    else:
        request["ConsistentRead"] = True

    items: list[dict[str, Any]] = []

    while True:
        response = client.query(**request)

        items.extend(plain_attributes(item) for item in response.get("Items", []))

        cursor = response.get("LastEvaluatedKey")

        if not cursor:
            return items

        request["ExclusiveStartKey"] = cursor


def plain_attributes(item: dict[str, Any]) -> dict[str, Any]:
    return {key: deserialize_attribute(value) for key, value in item.items()}


def manifest_document(
    run: dict[str, Any],
    snapshots: list[dict[str, Any]],
    frontier: list[dict[str, Any]],
) -> dict[str, Any]:
    archive_id = string_from_item(run, "archiveId", "capture run")
    seed_url = string_from_item(run, "seedUrl", "capture run")
    created_at = string_from_item(run, "closedAt", "capture run")

    document: dict[str, Any] = {
        "schemaVersion": MANIFEST_SCHEMA_VERSION,
        "archiveId": archive_id,
        "normalizerVersion": optional_string(run, "normalizerVersion")
        or DEFAULT_NORMALIZER_VERSION,
        "seedUrl": seed_url,
        "createdAt": created_at,
        "snapshots": [snapshot_entry(item) for item in snapshots],
        "failedPages": [
            {
                "urlKey": item["urlKey"],
                "reasonCode": item.get("failureReason") or "capture_failed",
            }
            for item in frontier
            if item.get("state") == "FAILED"
        ],
    }

    collection_id = optional_string(run, "collectionId")

    if collection_id is not None:
        document["collectionId"] = collection_id

    return document


def seed_succeeded(run: dict[str, Any], frontier: list[dict[str, Any]]) -> bool:
    seed_key = identify_url(string_from_item(run, "seedUrl", "capture run")).url_key

    return any(
        item.get("urlKey") == seed_key and item.get("state") == "COMPLETED" for item in frontier
    )


def snapshot_entry(item: dict[str, Any]) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "snapshotId": item["snapshotId"],
        "urlKey": item["urlKey"],
        "url": item["url"],
        "finalUrl": item["finalUrl"],
        "capturedAt": item["capturedAt"],
        "warcArtifacts": [artifact_fields(ref) for ref in item["warcArtifacts"]],
    }

    if "redirectChain" in item:
        entry["redirectChain"] = item["redirectChain"]

    if "minDepth" in item:
        entry["minDepth"] = item["minDepth"]

    if "contentType" in item:
        entry["contentType"] = item["contentType"]

    return entry


def artifact_fields(raw: dict[str, Any]) -> dict[str, Any]:
    reference = ArtifactReference(
        bucket=raw["bucket"],
        key=raw["key"],
        sha256=raw["sha256"],
        size_bytes=raw["sizeBytes"],
        version_id=raw.get("versionId"),
    )

    fields: dict[str, Any] = {
        "bucket": reference.bucket,
        "key": reference.key,
        "sha256": reference.sha256,
        "sizeBytes": reference.size_bytes,
    }

    if reference.version_id is not None:
        fields["versionId"] = reference.version_id

    return fields


def is_crawl_completed_message(
    item: dict[str, Any],
    archive_id: str,
    manifest_digest: str,
) -> bool:
    payload = item.get("payload", {}).get("M", {})

    return (
        item.get("type", {}).get("S") == "CrawlCompleted"
        and item.get("correlationId", {}).get("S") == archive_id
        and payload.get("archiveId", {}).get("S") == archive_id
        and payload.get("manifestDigest", {}).get("S") == manifest_digest
    )
