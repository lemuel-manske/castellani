from datetime import UTC, datetime
from typing import Any

from domain import (
    ArtifactReference,
    CaptureOutcome,
    DiscoveredPage,
    PageTask,
    TaskClaim,
)
from tables import FRONTIER_TABLE, OUTBOX_TABLE, RUNS_TABLE, SNAPSHOTS_TABLE


def claim_from_item(
    archive_id: str,
    url_key: str,
    item: dict[str, Any],
) -> TaskClaim:
    try:
        task = PageTask(
            archive_id=archive_id,
            url_key=url_key,
            url=item["url"]["S"],
            depth=int(item["depth"]["N"]),
        )

        return TaskClaim(
            task=task,
            attempt_id=item["attemptId"]["S"],
            fence=int(item["fence"]["N"]),
            lease_until=float(item["leaseUntil"]["N"]),
        )
    except (KeyError, TypeError, ValueError) as error:
        raise RuntimeError("DynamoDB returned an invalid page-task claim") from error


def read_run(client: Any, archive_id: str) -> dict[str, Any] | None:
    response = client.get_item(
        TableName=RUNS_TABLE,
        Key={"archiveId": {"S": archive_id}},
        ConsistentRead=True,
    )

    item = response.get("Item")

    return item if item else None


def read_frontier(
    client: Any,
    archive_id: str,
    url_key: str,
) -> dict[str, Any] | None:
    response = client.get_item(
        TableName=FRONTIER_TABLE,
        Key={
            "archiveId": {"S": archive_id},
            "urlKey": {"S": url_key},
        },
        ConsistentRead=True,
    )

    item = response.get("Item")

    return item if item else None


def read_outbox(client: Any, message_id: str) -> dict[str, Any] | None:
    response = client.get_item(
        TableName=OUTBOX_TABLE,
        Key={"messageId": {"S": message_id}},
        ConsistentRead=True,
    )

    item = response.get("Item")

    return item if item else None


def claim_task_transaction(
    archive_id: str,
    url_key: str,
    attempt_id: str,
    lease_until: float,
    now: float,
) -> list[dict[str, Any]]:
    return [
        {
            "ConditionCheck": {
                "TableName": RUNS_TABLE,
                "Key": {"archiveId": {"S": archive_id}},
                "ConditionExpression": "#admission = :open",
                "ExpressionAttributeNames": {"#admission": "admission"},
                "ExpressionAttributeValues": {":open": {"S": "OPEN"}},
            }
        },
        {
            "Update": {
                "TableName": FRONTIER_TABLE,
                "Key": {
                    "archiveId": {"S": archive_id},
                    "urlKey": {"S": url_key},
                },
                "UpdateExpression": (
                    "SET #state = :claimed, #attempt = :attempt, "
                    "#lease = :lease, #fence = if_not_exists(#fence, :zero) + :one"
                ),
                "ConditionExpression": (
                    "#state = :pending OR (#state = :claimed AND #lease <= :now)"
                ),
                "ExpressionAttributeNames": {
                    "#state": "state",
                    "#attempt": "attemptId",
                    "#lease": "leaseUntil",
                    "#fence": "fence",
                },
                "ExpressionAttributeValues": {
                    ":pending": {"S": "PENDING"},
                    ":claimed": {"S": "CLAIMED"},
                    ":attempt": {"S": attempt_id},
                    ":lease": {"N": str(lease_until)},
                    ":now": {"N": str(now)},
                    ":zero": {"N": "0"},
                    ":one": {"N": "1"},
                },
            }
        },
    ]


def renew_task_transaction(
    archive_id: str,
    url_key: str,
    attempt_id: str,
    fence: int,
    lease_until: float,
    now: float,
) -> list[dict[str, Any]]:
    return [
        {
            "ConditionCheck": {
                "TableName": RUNS_TABLE,
                "Key": {"archiveId": {"S": archive_id}},
                "ConditionExpression": "#admission = :open",
                "ExpressionAttributeNames": {"#admission": "admission"},
                "ExpressionAttributeValues": {":open": {"S": "OPEN"}},
            }
        },
        {
            "Update": {
                "TableName": FRONTIER_TABLE,
                "Key": {
                    "archiveId": {"S": archive_id},
                    "urlKey": {"S": url_key},
                },
                "UpdateExpression": "SET #lease = :lease",
                "ConditionExpression": (
                    "#state = :claimed AND #attempt = :attempt "
                    "AND #fence = :fence AND #lease > :now"
                ),
                "ExpressionAttributeNames": {
                    "#state": "state",
                    "#attempt": "attemptId",
                    "#fence": "fence",
                    "#lease": "leaseUntil",
                },
                "ExpressionAttributeValues": {
                    ":claimed": {"S": "CLAIMED"},
                    ":attempt": {"S": attempt_id},
                    ":fence": {"N": str(fence)},
                    ":lease": {"N": str(lease_until)},
                    ":now": {"N": str(now)},
                },
            }
        },
    ]


def complete_task_transaction(
    outcome: CaptureOutcome,
    depth: int,
    message_id: str,
    now: float,
) -> list[dict[str, Any]]:
    capture = outcome.capture
    occurred_at = _isoformat(datetime.fromtimestamp(now, UTC))
    captured_at = capture.captured_at

    if captured_at.tzinfo is None:
        captured_at = captured_at.replace(tzinfo=UTC)

    captured_at_text = _isoformat(captured_at)
    artifacts = [_artifact_attribute(item) for item in outcome.warc_artifacts]
    snapshot_item: dict[str, Any] = {
        "snapshotId": {"S": outcome.snapshot_id},
        "archiveId": {"S": outcome.archive_id},
        "urlKey": {"S": outcome.url_key},
        "url": {"S": capture.requested_url},
        "finalUrl": {"S": capture.final_url},
        "capturedAt": {"S": captured_at_text},
        "minDepth": {"N": str(depth)},
        "redirectChain": {"L": [{"S": url} for url in capture.redirect_chain]},
        "warcArtifacts": {"L": artifacts},
    }

    if capture.content_type is not None:
        snapshot_item["contentType"] = {"S": capture.content_type}

    if capture.title:
        snapshot_item["title"] = {"S": capture.title}

    if capture.status_code is not None:
        snapshot_item["statusCode"] = {"N": str(capture.status_code)}

    payload: dict[str, Any] = {
        "archiveId": {"S": outcome.archive_id},
        "snapshotId": {"S": outcome.snapshot_id},
        "urlKey": {"S": outcome.url_key},
        "url": {"S": capture.requested_url},
        "finalUrl": {"S": capture.final_url},
        "redirectChain": {"L": [{"S": url} for url in capture.redirect_chain]},
        "capturedAt": {"S": captured_at_text},
        "warcArtifacts": {"L": artifacts},
    }

    if capture.content_type is not None:
        payload["contentType"] = {"S": capture.content_type}

    return [
        {
            "Update": {
                "TableName": FRONTIER_TABLE,
                "Key": {
                    "archiveId": {"S": outcome.archive_id},
                    "urlKey": {"S": outcome.url_key},
                },
                "UpdateExpression": (
                    "SET #state = :completed, #snapshot = :snapshot, "
                    "#capture_url = :capture_url, #final_url = :final_url, "
                    "#captured_at = :captured_at, #redirects = :redirects, "
                    "#artifacts = :artifacts, #min_depth = :min_depth "
                    "REMOVE #attempt, #lease"
                ),
                "ConditionExpression": (
                    "#state = :claimed AND #attempt = :attempt "
                    "AND #fence = :fence AND #lease > :now"
                ),
                "ExpressionAttributeNames": {
                    "#state": "state",
                    "#attempt": "attemptId",
                    "#fence": "fence",
                    "#lease": "leaseUntil",
                    "#snapshot": "snapshotId",
                    "#capture_url": "capturedUrl",
                    "#final_url": "finalUrl",
                    "#captured_at": "capturedAt",
                    "#redirects": "redirectChain",
                    "#artifacts": "warcArtifacts",
                    "#min_depth": "minDepth",
                },
                "ExpressionAttributeValues": {
                    ":claimed": {"S": "CLAIMED"},
                    ":completed": {"S": "COMPLETED"},
                    ":attempt": {"S": outcome.attempt_id},
                    ":fence": {"N": str(outcome.fence)},
                    ":now": {"N": str(now)},
                    ":snapshot": {"S": outcome.snapshot_id},
                    ":capture_url": {"S": capture.requested_url},
                    ":final_url": {"S": capture.final_url},
                    ":captured_at": {"S": captured_at_text},
                    ":redirects": {"L": [{"S": url} for url in capture.redirect_chain]},
                    ":artifacts": {"L": artifacts},
                    ":min_depth": {"N": str(depth)},
                },
            }
        },
        {
            "Update": {
                "TableName": RUNS_TABLE,
                "Key": {"archiveId": {"S": outcome.archive_id}},
                "UpdateExpression": "ADD #outstanding :minus_one, #completed :one",
                "ConditionExpression": ("#admission = :open AND #outstanding >= :one"),
                "ExpressionAttributeNames": {
                    "#admission": "admission",
                    "#outstanding": "outstandingPages",
                    "#completed": "completedPages",
                },
                "ExpressionAttributeValues": {
                    ":open": {"S": "OPEN"},
                    ":minus_one": {"N": "-1"},
                    ":one": {"N": "1"},
                },
            }
        },
        {
            "Put": {
                "TableName": SNAPSHOTS_TABLE,
                "Item": snapshot_item,
                "ConditionExpression": "attribute_not_exists(#snapshot_id)",
                "ExpressionAttributeNames": {"#snapshot_id": "snapshotId"},
            }
        },
        {
            "Put": {
                "TableName": OUTBOX_TABLE,
                "Item": {
                    "messageId": {"S": message_id},
                    "correlationId": {"S": outcome.archive_id},
                    "type": {"S": "PageCaptured"},
                    "version": {"N": "1"},
                    "occurredAt": {"S": occurred_at},
                    "payload": {"M": payload},
                    "status": {"S": "PENDING"},
                    "attempts": {"N": "0"},
                    "nextAttemptAt": {"N": str(now)},
                },
                "ConditionExpression": "attribute_not_exists(#message_id)",
                "ExpressionAttributeNames": {"#message_id": "messageId"},
            }
        },
    ]


def admit_page_transaction(
    claim: TaskClaim,
    page: DiscoveredPage,
    message_id: str,
    now: float,
) -> list[dict[str, Any]]:
    archive_id = claim.task.archive_id
    url_key = page.identity.url_key
    occurred_at = _isoformat(datetime.fromtimestamp(now, UTC))

    return [
        {
            "ConditionCheck": {
                "TableName": FRONTIER_TABLE,
                "Key": {
                    "archiveId": {"S": archive_id},
                    "urlKey": {"S": claim.task.url_key},
                },
                "ConditionExpression": (
                    "#state = :claimed AND #attempt = :attempt "
                    "AND #fence = :fence AND #lease > :now"
                ),
                "ExpressionAttributeNames": {
                    "#state": "state",
                    "#attempt": "attemptId",
                    "#fence": "fence",
                    "#lease": "leaseUntil",
                },
                "ExpressionAttributeValues": {
                    ":claimed": {"S": "CLAIMED"},
                    ":attempt": {"S": claim.attempt_id},
                    ":fence": {"N": str(claim.fence)},
                    ":now": {"N": str(now)},
                },
            }
        },
        {
            "Update": {
                "TableName": RUNS_TABLE,
                "Key": {"archiveId": {"S": archive_id}},
                "UpdateExpression": (
                    "SET #admitted = if_not_exists(#admitted, :zero) + :one, "
                    "#outstanding = if_not_exists(#outstanding, :zero) + :one"
                ),
                "ConditionExpression": (
                    "#admission = :open AND attribute_exists(#maximum) "
                    "AND attribute_exists(#admitted) AND attribute_exists(#outstanding) "
                    "AND #admitted < #maximum"
                ),
                "ExpressionAttributeNames": {
                    "#admission": "admission",
                    "#admitted": "admittedPages",
                    "#maximum": "maxPages",
                    "#outstanding": "outstandingPages",
                },
                "ExpressionAttributeValues": {
                    ":open": {"S": "OPEN"},
                    ":zero": {"N": "0"},
                    ":one": {"N": "1"},
                },
            }
        },
        {
            "Put": {
                "TableName": FRONTIER_TABLE,
                "Item": {
                    "archiveId": {"S": archive_id},
                    "urlKey": {"S": url_key},
                    "url": {"S": page.identity.navigation_url},
                    "navigationUrl": {"S": page.identity.navigation_url},
                    "fetchUrl": {"S": page.identity.fetch_url},
                    "discoveryUrl": {"S": page.identity.discovery_url},
                    "identityVersion": {"N": "1"},
                    "depth": {"N": str(page.depth)},
                    "state": {"S": "PENDING"},
                },
                "ConditionExpression": "attribute_not_exists(#url_key)",
                "ExpressionAttributeNames": {"#url_key": "urlKey"},
            }
        },
        {
            "Put": {
                "TableName": OUTBOX_TABLE,
                "Item": {
                    "messageId": {"S": message_id},
                    "correlationId": {"S": archive_id},
                    "type": {"S": "CapturePage"},
                    "version": {"N": "1"},
                    "occurredAt": {"S": occurred_at},
                    "payload": {
                        "M": {
                            "archiveId": {"S": archive_id},
                            "urlKey": {"S": url_key},
                        }
                    },
                    "status": {"S": "PENDING"},
                    "attempts": {"N": "0"},
                    "nextAttemptAt": {"N": str(now)},
                },
                "ConditionExpression": "attribute_not_exists(#message_id)",
                "ExpressionAttributeNames": {"#message_id": "messageId"},
            }
        },
    ]


def release_task_transaction(
    claim: TaskClaim,
    message_id: str,
    now: float,
) -> list[dict[str, Any]]:
    occurred_at = _isoformat(datetime.fromtimestamp(now, UTC))

    return [
        {
            "ConditionCheck": {
                "TableName": RUNS_TABLE,
                "Key": {"archiveId": {"S": claim.task.archive_id}},
                "ConditionExpression": "#admission = :open",
                "ExpressionAttributeNames": {"#admission": "admission"},
                "ExpressionAttributeValues": {":open": {"S": "OPEN"}},
            }
        },
        {
            "Update": {
                "TableName": FRONTIER_TABLE,
                "Key": {
                    "archiveId": {"S": claim.task.archive_id},
                    "urlKey": {"S": claim.task.url_key},
                },
                "UpdateExpression": "SET #state = :pending REMOVE #attempt, #lease",
                "ConditionExpression": (
                    "#state = :claimed AND #attempt = :attempt "
                    "AND #fence = :fence AND #lease > :now"
                ),
                "ExpressionAttributeNames": {
                    "#state": "state",
                    "#attempt": "attemptId",
                    "#fence": "fence",
                    "#lease": "leaseUntil",
                },
                "ExpressionAttributeValues": {
                    ":pending": {"S": "PENDING"},
                    ":claimed": {"S": "CLAIMED"},
                    ":attempt": {"S": claim.attempt_id},
                    ":fence": {"N": str(claim.fence)},
                    ":now": {"N": str(now)},
                },
            }
        },
        {
            "Put": {
                "TableName": OUTBOX_TABLE,
                "Item": {
                    "messageId": {"S": message_id},
                    "correlationId": {"S": claim.task.archive_id},
                    "type": {"S": "CapturePage"},
                    "version": {"N": "1"},
                    "occurredAt": {"S": occurred_at},
                    "payload": {
                        "M": {
                            "archiveId": {"S": claim.task.archive_id},
                            "urlKey": {"S": claim.task.url_key},
                        }
                    },
                    "status": {"S": "PENDING"},
                    "attempts": {"N": "0"},
                    "nextAttemptAt": {"N": str(now)},
                },
                "ConditionExpression": "attribute_not_exists(#message_id)",
                "ExpressionAttributeNames": {"#message_id": "messageId"},
            }
        },
    ]


def finish_task(
    client: Any,
    archive_id: str,
    url_key: str,
    attempt_id: str,
    fence: int,
    state: str,
    reason_code: str | None,
    message: str | None,
    now: float,
) -> None:
    names = {
        "#state": "state",
        "#attempt": "attemptId",
        "#fence": "fence",
        "#lease": "leaseUntil",
    }
    values: dict[str, Any] = {
        ":claimed": {"S": "CLAIMED"},
        ":attempt": {"S": attempt_id},
        ":fence": {"N": str(fence)},
        ":state": {"S": state},
        ":now": {"N": str(now)},
    }
    update = "SET #state = :state REMOVE #attempt, #lease"

    if reason_code is not None and message is not None:
        names.update({"#reason": "failureReason", "#message": "failureMessage"})
        values.update(
            {
                ":reason": {"S": reason_code},
                ":message": {"S": message},
            }
        )
        update = (
            "SET #state = :state, #reason = :reason, #message = :message REMOVE #attempt, #lease"
        )

    client.update_item(
        TableName=FRONTIER_TABLE,
        Key={"archiveId": {"S": archive_id}, "urlKey": {"S": url_key}},
        UpdateExpression=update,
        ConditionExpression=(
            "#state = :claimed AND #attempt = :attempt AND #fence = :fence AND #lease > :now"
        ),
        ExpressionAttributeNames=names,
        ExpressionAttributeValues=values,
    )


def is_page_captured_message(
    item: dict[str, Any],
    archive_id: str,
    snapshot_id: str,
) -> bool:
    payload = item.get("payload", {}).get("M", {})

    return (
        item.get("type", {}).get("S") == "PageCaptured"
        and item.get("correlationId", {}).get("S") == archive_id
        and payload.get("archiveId", {}).get("S") == archive_id
        and payload.get("snapshotId", {}).get("S") == snapshot_id
    )


def is_release_message(item: dict[str, Any], claim: TaskClaim) -> bool:
    payload = item.get("payload", {}).get("M", {})

    return (
        item.get("correlationId", {}).get("S") == claim.task.archive_id
        and item.get("type", {}).get("S") == "CapturePage"
        and payload.get("archiveId", {}).get("S") == claim.task.archive_id
        and payload.get("urlKey", {}).get("S") == claim.task.url_key
    )


def _artifact_attribute(artifact: ArtifactReference) -> dict[str, Any]:
    values: dict[str, Any] = {
        "bucket": {"S": artifact.bucket},
        "key": {"S": artifact.key},
        "sha256": {"S": artifact.sha256},
        "sizeBytes": {"N": str(artifact.size_bytes)},
    }

    if artifact.version_id is not None:
        values["versionId"] = {"S": artifact.version_id}

    return {"M": values}


def _isoformat(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")
