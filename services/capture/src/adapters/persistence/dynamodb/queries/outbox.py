from typing import Any

from ..values import (
    deserialize_attribute,
    number_from_item,
    string_from_item,
)

_OUTBOX_INDEX = "status-nextAttemptAt-index"
_CLAIM_LIMIT = 50


def query_due_messages(
    client: Any,
    table_name: str,
    status: str,
    now: float,
    cursor: dict[str, Any] | None,
) -> dict[str, Any]:
    request: dict[str, Any] = {
        "TableName": table_name,
        "IndexName": _OUTBOX_INDEX,
        "KeyConditionExpression": "#status = :status AND #next_attempt <= :now",
        "ExpressionAttributeNames": {
            "#status": "status",
            "#next_attempt": "nextAttemptAt",
        },
        "ExpressionAttributeValues": {
            ":status": {"S": status},
            ":now": {"N": str(now)},
        },
        "Limit": _CLAIM_LIMIT,
    }

    if cursor is not None:
        request["ExclusiveStartKey"] = cursor

    return client.query(**request)


def claim_message(
    client: Any,
    table_name: str,
    message_id: str,
    status: str,
    claimed_status: str,
    due_at: str,
    lease_token: str,
    lease_until: float,
) -> dict[str, Any]:
    return client.update_item(
        TableName=table_name,
        Key={"messageId": {"S": message_id}},
        ConditionExpression="#status = :status AND #next_attempt = :due_at",
        UpdateExpression=(
            "SET #status = :claimed, #lease_token = :lease_token, "
            "#next_attempt = :lease_until ADD #attempts :one"
        ),
        ExpressionAttributeNames={
            "#status": "status",
            "#next_attempt": "nextAttemptAt",
            "#lease_token": "leaseToken",
            "#attempts": "attempts",
        },
        ExpressionAttributeValues={
            ":status": {"S": status},
            ":due_at": {"N": due_at},
            ":claimed": {"S": claimed_status},
            ":lease_token": {"S": lease_token},
            ":lease_until": {"N": str(lease_until)},
            ":one": {"N": "1"},
        },
        ReturnValues="ALL_NEW",
    )


def confirm_message(
    client: Any,
    table_name: str,
    message_id: str,
    lease_token: str,
    claimed_status: str,
    published_status: str,
    published_at: str,
    now: float,
) -> None:
    client.update_item(
        TableName=table_name,
        Key={"messageId": {"S": message_id}},
        ConditionExpression=(
            "#status = :claimed AND #lease_token = :lease_token AND #next_attempt > :lease_now"
        ),
        UpdateExpression=("SET #status = :published, #published_at = :now REMOVE #lease_token"),
        ExpressionAttributeNames={
            "#status": "status",
            "#lease_token": "leaseToken",
            "#published_at": "publishedAt",
            "#next_attempt": "nextAttemptAt",
        },
        ExpressionAttributeValues={
            ":claimed": {"S": claimed_status},
            ":lease_token": {"S": lease_token},
            ":published": {"S": published_status},
            ":now": {"S": published_at},
            ":lease_now": {"N": str(now)},
        },
    )


def reschedule_message(
    client: Any,
    table_name: str,
    message_id: str,
    lease_token: str,
    claimed_status: str,
    pending_status: str,
    next_attempt_at: float,
    now: float,
) -> None:
    client.update_item(
        TableName=table_name,
        Key={"messageId": {"S": message_id}},
        ConditionExpression=(
            "#status = :claimed AND #lease_token = :lease_token AND #next_attempt > :now"
        ),
        UpdateExpression=(
            "SET #status = :pending, #next_attempt = :next_attempt REMOVE #lease_token"
        ),
        ExpressionAttributeNames={
            "#status": "status",
            "#lease_token": "leaseToken",
            "#next_attempt": "nextAttemptAt",
        },
        ExpressionAttributeValues={
            ":claimed": {"S": claimed_status},
            ":lease_token": {"S": lease_token},
            ":pending": {"S": pending_status},
            ":next_attempt": {"N": str(next_attempt_at)},
            ":now": {"N": str(now)},
        },
    )


def message_from_item(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "messageId": string_from_item(item, "messageId", "outbox record"),
        "correlationId": string_from_item(item, "correlationId", "outbox record"),
        "type": string_from_item(item, "type", "outbox record"),
        "version": number_from_item(item, "version", "outbox record"),
        "occurredAt": string_from_item(item, "occurredAt", "outbox record"),
        "payload": deserialize_attribute(item.get("payload", {})),
    }
