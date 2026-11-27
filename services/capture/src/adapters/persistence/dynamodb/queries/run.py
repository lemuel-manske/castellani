from datetime import UTC, datetime
from typing import Any

from contracts.messages import CAPTURE_PAGE_EVENT, CapturePagePayload
from domain.capture import ADMISSION_OPEN, TASK_PENDING, StartCrawl, identify_url
from topology.tables import FRONTIER_TABLE, RUNS_TABLE

from .common import outbox_put


def seed_run_transaction(
    start: StartCrawl,
    message_id: str,
    now: float,
) -> list[dict[str, Any]]:
    identity = identify_url(start.seed_url)
    occurred_at = datetime.fromtimestamp(now, UTC).isoformat().replace("+00:00", "Z")

    run_item: dict[str, Any] = {
        "archiveId": {"S": start.archive_id},
        "admission": {"S": ADMISSION_OPEN},
        "seedUrl": {"S": start.seed_url},
        "maxDepth": {"N": str(start.max_depth)},
        "maxPages": {"N": str(start.max_pages)},
        "admittedPages": {"N": "1"},
        "outstandingPages": {"N": "1"},
        "completedPages": {"N": "0"},
        "failedPages": {"N": "0"},
        "createdAt": {"S": occurred_at},
        "updatedAt": {"S": occurred_at},
    }

    if start.collection_id is not None:
        run_item["collectionId"] = {"S": start.collection_id}

    if start.allowed_origins:
        run_item["allowedOrigins"] = {"SS": list(start.allowed_origins)}

    if start.auth_generation is not None:
        run_item["authGeneration"] = {"N": str(start.auth_generation)}

    if start.normalizer_version is not None:
        run_item["normalizerVersion"] = {"S": start.normalizer_version}

    payload: CapturePagePayload = {
        "archiveId": start.archive_id,
        "urlKey": identity.url_key,
    }

    return [
        {
            "Put": {
                "TableName": RUNS_TABLE,
                "Item": run_item,
                "ConditionExpression": "attribute_not_exists(#archive_id)",
                "ExpressionAttributeNames": {"#archive_id": "archiveId"},
            }
        },
        {
            "Put": {
                "TableName": FRONTIER_TABLE,
                "Item": {
                    "archiveId": {"S": start.archive_id},
                    "urlKey": {"S": identity.url_key},
                    "url": {"S": identity.navigation_url},
                    "navigationUrl": {"S": identity.navigation_url},
                    "fetchUrl": {"S": identity.fetch_url},
                    "discoveryUrl": {"S": identity.discovery_url},
                    "identityVersion": {"N": "1"},
                    "depth": {"N": "0"},
                    "state": {"S": TASK_PENDING},
                },
                "ConditionExpression": "attribute_not_exists(#url_key)",
                "ExpressionAttributeNames": {"#url_key": "urlKey"},
            }
        },
        outbox_put(
            message_id=message_id,
            correlation_id=start.archive_id,
            message_type=CAPTURE_PAGE_EVENT,
            occurred_at=occurred_at,
            payload=payload,
            now=now,
        ),
    ]
