from collections.abc import Mapping
from typing import Any

from topology.tables import OUTBOX_TABLE

from ..values import serialize_map


def with_cursor(
    request: dict[str, Any],
    cursor: dict[str, Any] | None,
) -> dict[str, Any]:
    if cursor is None:
        return request

    return {**request, "ExclusiveStartKey": cursor}


def outbox_put(
    message_id: str,
    correlation_id: str,
    message_type: str,
    occurred_at: str,
    payload: Mapping[str, object],
    now: float,
) -> dict[str, Any]:
    return {
        "Put": {
            "TableName": OUTBOX_TABLE,
            "Item": {
                "messageId": {"S": message_id},
                "correlationId": {"S": correlation_id},
                "type": {"S": message_type},
                "version": {"N": "1"},
                "occurredAt": {"S": occurred_at},
                "payload": {"M": serialize_map(payload)},
                "status": {"S": "PENDING"},
                "attempts": {"N": "0"},
                "nextAttemptAt": {"N": str(now)},
            },
            "ConditionExpression": "attribute_not_exists(#message_id)",
            "ExpressionAttributeNames": {"#message_id": "messageId"},
        }
    }


def fence_condition(
    attempt_id: str,
    fence: int,
    now: float,
    lease_until: float | None = None,
) -> tuple[str, dict[str, str], dict[str, Any]]:
    values: dict[str, Any] = {
        ":claimed": {"S": "CLAIMED"},
        ":attempt": {"S": attempt_id},
        ":fence": {"N": str(fence)},
    }

    if lease_until is not None:
        values[":lease"] = {"N": str(lease_until)}

    values[":now"] = {"N": str(now)}

    return (
        "#state = :claimed AND #attempt = :attempt AND #fence = :fence AND #lease > :now",
        {
            "#state": "state",
            "#attempt": "attemptId",
            "#fence": "fence",
            "#lease": "leaseUntil",
        },
        values,
    )


def reservation_condition(
    attempt_id: str,
    reservation_id: str,
    fence: int,
    now: float | None = None,
    lease_until: float | None = None,
) -> tuple[str, dict[str, str], dict[str, Any]]:
    values: dict[str, Any] = {
        ":attempt": {"S": attempt_id},
        ":reservation": {"S": reservation_id},
        ":fence": {"N": str(fence)},
    }

    condition = "#owner = :attempt AND #reservation = :reservation AND #fence = :fence"

    if lease_until is not None:
        values[":lease"] = {"N": str(lease_until)}

    if now is not None:
        condition += " AND #lease > :now"
        values[":now"] = {"N": str(now)}

    return (
        condition,
        {
            "#owner": "ownerAttemptId",
            "#reservation": "reservationId",
            "#fence": "fence",
            "#lease": "leaseUntil",
        },
        values,
    )
