from typing import Any

from domain.capture import PACKAGE_PENDING, identify_url
from topology.tables import FRONTIER_TABLE, OUTBOX_TABLE, RUNS_TABLE, SNAPSHOTS_TABLE

from ..values import deserialize_attribute

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


def seed_succeeded(run: dict[str, Any], frontier: list[dict[str, Any]]) -> bool:
    seed_key = identify_url(run["seedUrl"]).url_key

    return any(
        item.get("urlKey") == seed_key and item.get("state") == "COMPLETED" for item in frontier
    )


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


def is_published_manifest(item: dict[str, Any], digest: str) -> bool:
    return (
        item.get("manifestStatus", {}).get("S") == "PUBLISHED"
        and item.get("manifestDigest", {}).get("S") == digest
    )


def dynamodb_artifact_map(artifact: dict[str, Any]) -> dict[str, Any]:
    values: dict[str, Any] = {
        "bucket": {"S": artifact["bucket"]},
        "key": {"S": artifact["key"]},
        "sha256": {"S": artifact["sha256"]},
        "sizeBytes": {"N": str(artifact["sizeBytes"])},
    }

    if "versionId" in artifact:
        values["versionId"] = {"S": artifact["versionId"]}

    return values


def envelope_attributes(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "archiveId": {"S": payload["archiveId"]},
        "manifest": {"M": dynamodb_artifact_map(payload["manifest"])},
        "manifestDigest": {"S": payload["manifestDigest"]},
        "seedSucceeded": {"BOOL": payload["seedSucceeded"]},
        "capturedCount": {"N": str(payload["capturedCount"])},
        "failedCount": {"N": str(payload["failedCount"])},
    }


def finalize_transaction(
    archive_id: str,
    artifact: dict[str, Any],
    digest: str,
    occurred_at: str,
    message_id: str,
    now: float,
    seed_ok: bool,
    captured_count: int,
    failed_count: int,
) -> list[dict[str, Any]]:
    payload: dict[str, Any] = {
        "archiveId": archive_id,
        "manifest": artifact,
        "manifestDigest": digest,
        "seedSucceeded": seed_ok,
        "capturedCount": captured_count,
        "failedCount": failed_count,
    }

    update_expression = "SET #status = :published, #key = :key, #digest = :digest"
    names: dict[str, Any] = {
        "#status": "manifestStatus",
        "#key": "manifestKey",
        "#digest": "manifestDigest",
    }
    values: dict[str, Any] = {
        ":pending": {"S": "PENDING"},
        ":published": {"S": "PUBLISHED"},
        ":key": {"S": artifact["key"]},
        ":digest": {"S": digest},
    }

    if seed_ok:
        update_expression += ", #package_status = :package_pending"
        names["#package_status"] = "packageStatus"
        values[":package_pending"] = {"S": PACKAGE_PENDING}

    return [
        {
            "Update": {
                "TableName": RUNS_TABLE,
                "Key": {"archiveId": {"S": archive_id}},
                "UpdateExpression": update_expression,
                "ConditionExpression": "#status = :pending",
                "ExpressionAttributeNames": names,
                "ExpressionAttributeValues": values,
            }
        },
        {
            "Put": {
                "TableName": OUTBOX_TABLE,
                "Item": {
                    "messageId": {"S": message_id},
                    "correlationId": {"S": archive_id},
                    "type": {"S": "CrawlCompleted"},
                    "version": {"N": "1"},
                    "occurredAt": {"S": occurred_at},
                    "payload": {"M": envelope_attributes(payload)},
                    "status": {"S": "PENDING"},
                    "attempts": {"N": "0"},
                    "nextAttemptAt": {"N": str(now)},
                },
                "ConditionExpression": "attribute_not_exists(#message_id)",
                "ExpressionAttributeNames": {"#message_id": "messageId"},
            }
        },
    ]
