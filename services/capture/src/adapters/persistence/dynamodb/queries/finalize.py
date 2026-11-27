from typing import Any

from adapters.serialization import artifact_reference
from contracts.messages import CRAWL_COMPLETED_EVENT, CrawlCompletedPayload
from contracts.types import ArtifactReferenceContract
from domain.capture import (
    MANIFEST_PENDING,
    MANIFEST_PUBLISHED,
    PACKAGE_PENDING,
    TASK_COMPLETED,
    TASK_FAILED,
    ManifestFailure,
    ManifestRun,
    ManifestSnapshot,
    ManifestSource,
    identify_url,
)
from topology.tables import FRONTIER_TABLE, RUNS_TABLE, SNAPSHOTS_TABLE

from ..values import envelope_matches, optional_string, plain_attributes
from .common import outbox_put, with_cursor

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
    cursor: dict[str, Any] | None = None

    while True:
        response = client.query(**with_cursor(request, cursor))

        items.extend(plain_attributes(item) for item in response.get("Items", []))

        cursor = response.get("LastEvaluatedKey")

        if not cursor:
            return items


def seed_succeeded(run: dict[str, Any], frontier: list[dict[str, Any]]) -> bool:
    seed_key = identify_url(run["seedUrl"]).url_key

    return any(
        item.get("urlKey") == seed_key and item.get("state") == TASK_COMPLETED for item in frontier
    )


def manifest_source(
    run: dict[str, Any],
    snapshots: list[dict[str, Any]],
    frontier: list[dict[str, Any]],
) -> ManifestSource:
    return ManifestSource(
        run=ManifestRun(
            archive_id=str(run["archiveId"]),
            seed_url=str(run["seedUrl"]),
            closed_at=str(run["closedAt"]),
            normalizer_version=run.get("normalizerVersion"),
            collection_id=run.get("collectionId"),
        ),
        snapshots=tuple(snapshot_from_item(item) for item in snapshots),
        failures=tuple(
            failure for item in frontier if (failure := failure_from_item(item)) is not None
        ),
        seed_succeeded=seed_succeeded(run, frontier),
    )


def snapshot_from_item(item: dict[str, Any]) -> ManifestSnapshot:
    return ManifestSnapshot(
        snapshot_id=str(item["snapshotId"]),
        url_key=str(item["urlKey"]),
        url=str(item["url"]),
        final_url=str(item["finalUrl"]),
        captured_at=str(item["capturedAt"]),
        warc_artifacts=tuple(artifact_reference(ref) for ref in item["warcArtifacts"]),
        redirect_chain=tuple(item["redirectChain"]) if "redirectChain" in item else None,
        min_depth=int(item["minDepth"]) if "minDepth" in item else None,
        content_type=str(item["contentType"]) if "contentType" in item else None,
    )


def failure_from_item(item: dict[str, Any]) -> ManifestFailure | None:
    if item.get("state") != TASK_FAILED:
        return None

    return ManifestFailure(
        url_key=str(item["urlKey"]),
        reason_code=str(item.get("failureReason") or "capture_failed"),
    )


def is_crawl_completed_message(
    item: dict[str, Any],
    archive_id: str,
    manifest_digest: str,
) -> bool:
    return envelope_matches(
        item,
        CRAWL_COMPLETED_EVENT,
        archive_id,
        {
            "archiveId": {"S": archive_id},
            "manifestDigest": {"S": manifest_digest},
        },
    )


def is_published_manifest(item: dict[str, Any], digest: str) -> bool:
    return (
        optional_string(item, "manifestStatus") == MANIFEST_PUBLISHED
        and optional_string(item, "manifestDigest") == digest
    )


def finalize_transaction(
    archive_id: str,
    artifact: ArtifactReferenceContract,
    digest: str,
    occurred_at: str,
    message_id: str,
    now: float,
    seed_ok: bool,
    captured_count: int,
    failed_count: int,
) -> list[dict[str, Any]]:
    payload: CrawlCompletedPayload = {
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
        ":pending": {"S": MANIFEST_PENDING},
        ":published": {"S": MANIFEST_PUBLISHED},
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
        outbox_put(
            message_id=message_id,
            correlation_id=archive_id,
            message_type=CRAWL_COMPLETED_EVENT,
            occurred_at=occurred_at,
            payload=payload,
            now=now,
        ),
    ]
