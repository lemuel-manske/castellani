from datetime import UTC, datetime
from typing import Any

from adapters.serialization import artifact_document
from contracts.messages import (
    CAPTURE_PAGE_EVENT,
    PAGE_CAPTURED_EVENT,
    CapturePagePayload,
    PageCapturedPayload,
)
from domain.capture import (
    DEFAULT_AUTH_GENERATION,
    ArtifactReference,
    CaptureOutcome,
    DiscoveredPage,
    PageTask,
    TaskClaim,
)
from topology.tables import FRONTIER_TABLE, OUTBOX_TABLE, RUNS_TABLE, SNAPSHOTS_TABLE
from utils.time import utc

from ..values import envelope_matches, number_from_item, optional_number
from .common import fence_condition, outbox_put


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


def auth_generation_changed(client: Any, archive_id: str, expected: int) -> bool:
    run = read_run(client, archive_id)

    if run is None:
        return False

    current = optional_number(run, "authGeneration")

    return (DEFAULT_AUTH_GENERATION if current is None else current) != expected


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


def read_depth(client: Any, archive_id: str, url_key: str) -> int:
    item = read_frontier(
        client,
        archive_id,
        url_key,
    )

    if item is None:
        raise RuntimeError("page-task disappeared before completion")

    return int(item.get("depth", {}).get("N", "0"))


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
    condition, names, values = fence_condition(
        attempt_id,
        fence,
        now,
        lease_until,
    )

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
                "ConditionExpression": condition,
                "ExpressionAttributeNames": names,
                "ExpressionAttributeValues": values,
            }
        },
    ]


def closes_run(run: dict[str, Any]) -> bool:
    return number_from_item(run, "outstandingPages", "capture run") == 1


def _closure_expression(
    now: float,
    names: dict[str, str],
    values: dict[str, Any],
) -> str:
    names.update(
        {
            "#admission": "admission",
            "#closed_at": "closedAt",
            "#manifest": "manifestStatus",
        }
    )
    values.update(
        {
            ":closed": {"S": "CLOSED"},
            ":closed_at": {"S": utc(datetime.fromtimestamp(now, UTC))},
            ":pending": {"S": "PENDING"},
        }
    )

    return "SET #admission = :closed, #closed_at = :closed_at, #manifest = :pending "


def completion_run_update(
    archive_id: str,
    auth_generation: int,
    now: float,
    close: bool,
) -> dict[str, Any]:
    names = {
        "#admission": "admission",
        "#outstanding": "outstandingPages",
        "#completed": "completedPages",
        "#auth_generation": "authGeneration",
    }
    values: dict[str, Any] = {
        ":open": {"S": "OPEN"},
        ":one": {"N": "1"},
        ":minus_one": {"N": "-1"},
        ":zero": {"N": "0"},
        ":auth_generation": {"N": str(auth_generation)},
    }
    expression = _closure_expression(now, names, values) if close else ""
    expression += "ADD #outstanding :minus_one, #completed :one"
    operator = "=" if close else ">"

    return {
        "Update": {
            "TableName": RUNS_TABLE,
            "Key": {"archiveId": {"S": archive_id}},
            "UpdateExpression": expression,
            "ConditionExpression": (
                f"#admission = :open AND #outstanding {operator} :one "
                "AND (#auth_generation = :auth_generation "
                "OR (:auth_generation = :zero AND attribute_not_exists(#auth_generation)))"
            ),
            "ExpressionAttributeNames": names,
            "ExpressionAttributeValues": values,
        }
    }


def failure_run_update(archive_id: str, now: float, close: bool) -> dict[str, Any]:
    names = {
        "#admission": "admission",
        "#outstanding": "outstandingPages",
        "#failed": "failedPages",
    }
    values: dict[str, Any] = {
        ":open": {"S": "OPEN"},
        ":one": {"N": "1"},
        ":minus_one": {"N": "-1"},
    }
    expression = _closure_expression(now, names, values) if close else ""
    expression += "ADD #outstanding :minus_one, #failed :one"
    operator = "=" if close else ">"

    return {
        "Update": {
            "TableName": RUNS_TABLE,
            "Key": {"archiveId": {"S": archive_id}},
            "UpdateExpression": expression,
            "ConditionExpression": f"#admission = :open AND #outstanding {operator} :one",
            "ExpressionAttributeNames": names,
            "ExpressionAttributeValues": values,
        }
    }


def complete_task_transaction(
    outcome: CaptureOutcome,
    depth: int,
    message_id: str,
    now: float,
    close: bool = False,
) -> list[dict[str, Any]]:
    capture = outcome.capture
    occurred_at = utc(datetime.fromtimestamp(now, UTC))
    captured_at = capture.captured_at

    if captured_at.tzinfo is None:
        captured_at = captured_at.replace(tzinfo=UTC)

    captured_at_text = utc(captured_at)
    artifacts = [artifact_attribute(item) for item in outcome.warc_artifacts]
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

    payload: PageCapturedPayload = {
        "archiveId": outcome.archive_id,
        "snapshotId": outcome.snapshot_id,
        "urlKey": outcome.url_key,
        "url": capture.requested_url,
        "finalUrl": capture.final_url,
        "redirectChain": list(capture.redirect_chain),
        "capturedAt": captured_at_text,
        "warcArtifacts": [artifact_document(item) for item in outcome.warc_artifacts],
    }

    if capture.content_type is not None:
        payload["contentType"] = capture.content_type

    condition, names, values = fence_condition(outcome.attempt_id, outcome.fence, now)

    names.update(
        {
            "#snapshot": "snapshotId",
            "#capture_url": "capturedUrl",
            "#final_url": "finalUrl",
            "#captured_at": "capturedAt",
            "#redirects": "redirectChain",
            "#artifacts": "warcArtifacts",
            "#min_depth": "minDepth",
        }
    )
    values.update(
        {
            ":completed": {"S": "COMPLETED"},
            ":snapshot": {"S": outcome.snapshot_id},
            ":capture_url": {"S": capture.requested_url},
            ":final_url": {"S": capture.final_url},
            ":captured_at": {"S": captured_at_text},
            ":redirects": {"L": [{"S": url} for url in capture.redirect_chain]},
            ":artifacts": {"L": artifacts},
            ":min_depth": {"N": str(depth)},
        }
    )

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
                "ConditionExpression": condition,
                "ExpressionAttributeNames": names,
                "ExpressionAttributeValues": values,
            }
        },
        completion_run_update(outcome.archive_id, outcome.auth_generation, now, close),
        {
            "Put": {
                "TableName": SNAPSHOTS_TABLE,
                "Item": snapshot_item,
                "ConditionExpression": "attribute_not_exists(#snapshot_id)",
                "ExpressionAttributeNames": {"#snapshot_id": "snapshotId"},
            }
        },
        outbox_put(
            message_id=message_id,
            correlation_id=outcome.archive_id,
            message_type=PAGE_CAPTURED_EVENT,
            occurred_at=occurred_at,
            payload=payload,
            now=now,
        ),
    ]


def admit_page_transaction(
    claim: TaskClaim,
    page: DiscoveredPage,
    message_id: str,
    now: float,
    auth_generation: int,
) -> list[dict[str, Any]]:
    archive_id = claim.task.archive_id
    url_key = page.identity.url_key
    occurred_at = utc(datetime.fromtimestamp(now, UTC))
    payload: CapturePagePayload = {"archiveId": archive_id, "urlKey": url_key}
    condition, names, values = fence_condition(claim.attempt_id, claim.fence, now)

    return [
        {
            "ConditionCheck": {
                "TableName": FRONTIER_TABLE,
                "Key": {
                    "archiveId": {"S": archive_id},
                    "urlKey": {"S": claim.task.url_key},
                },
                "ConditionExpression": condition,
                "ExpressionAttributeNames": names,
                "ExpressionAttributeValues": values,
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
                    "AND #admitted < #maximum "
                    "AND (#auth_generation = :auth_generation "
                    "OR (:auth_generation = :zero AND attribute_not_exists(#auth_generation)))"
                ),
                "ExpressionAttributeNames": {
                    "#admission": "admission",
                    "#admitted": "admittedPages",
                    "#maximum": "maxPages",
                    "#outstanding": "outstandingPages",
                    "#auth_generation": "authGeneration",
                },
                "ExpressionAttributeValues": {
                    ":open": {"S": "OPEN"},
                    ":zero": {"N": "0"},
                    ":one": {"N": "1"},
                    ":auth_generation": {"N": str(auth_generation)},
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
        outbox_put(
            message_id=message_id,
            correlation_id=archive_id,
            message_type=CAPTURE_PAGE_EVENT,
            occurred_at=occurred_at,
            payload=payload,
            now=now,
        ),
    ]


def release_task_transaction(
    claim: TaskClaim,
    message_id: str,
    now: float,
) -> list[dict[str, Any]]:
    occurred_at = utc(datetime.fromtimestamp(now, UTC))
    payload: CapturePagePayload = {
        "archiveId": claim.task.archive_id,
        "urlKey": claim.task.url_key,
    }
    condition, names, values = fence_condition(claim.attempt_id, claim.fence, now)
    values = {":pending": {"S": "PENDING"}, **values}

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
                "ConditionExpression": condition,
                "ExpressionAttributeNames": names,
                "ExpressionAttributeValues": values,
            }
        },
        outbox_put(
            message_id=message_id,
            correlation_id=claim.task.archive_id,
            message_type=CAPTURE_PAGE_EVENT,
            occurred_at=occurred_at,
            payload=payload,
            now=now,
        ),
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
    close: bool = False,
) -> None:
    condition, names, values = fence_condition(attempt_id, fence, now)
    values[":state"] = {"S": state}
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

    transaction: list[dict[str, Any]] = [
        {
            "Update": {
                "TableName": FRONTIER_TABLE,
                "Key": {"archiveId": {"S": archive_id}, "urlKey": {"S": url_key}},
                "UpdateExpression": update,
                "ConditionExpression": condition,
                "ExpressionAttributeNames": names,
                "ExpressionAttributeValues": values,
            }
        },
        failure_run_update(archive_id, now, close),
    ]

    client.transact_write_items(TransactItems=transaction)


def is_page_captured_message(
    item: dict[str, Any],
    archive_id: str,
    snapshot_id: str,
) -> bool:
    return envelope_matches(
        item,
        PAGE_CAPTURED_EVENT,
        archive_id,
        {
            "archiveId": {"S": archive_id},
            "snapshotId": {"S": snapshot_id},
        },
    )


def is_release_message(item: dict[str, Any], claim: TaskClaim) -> bool:
    return envelope_matches(
        item,
        CAPTURE_PAGE_EVENT,
        claim.task.archive_id,
        {
            "archiveId": {"S": claim.task.archive_id},
            "urlKey": {"S": claim.task.url_key},
        },
    )


def artifact_attribute(artifact: ArtifactReference) -> dict[str, Any]:
    values: dict[str, Any] = {
        "bucket": {"S": artifact.bucket},
        "key": {"S": artifact.key},
        "sha256": {"S": artifact.sha256},
        "sizeBytes": {"N": str(artifact.size_bytes)},
    }

    return {"M": values}
