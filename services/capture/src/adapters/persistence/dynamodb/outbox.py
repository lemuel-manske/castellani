import asyncio
import json
import time
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from botocore.exceptions import ClientError

from application.outbox import OutboxMessage


OUTBOX_PENDING = "PENDING"
OUTBOX_CLAIMED = "CLAIMED"
OUTBOX_PUBLISHED = "PUBLISHED"
OUTBOX_INDEX = "status-nextAttemptAt-index"
OUTBOX_CLAIM_LIMIT = 50


class OutboxLeaseLostError(RuntimeError):
    """Raised when an outbox message is no longer owned by this dispatcher."""


class DynamoDBOutbox:
    """Claims due outbox records and records their publication outcome."""

    def __init__(
        self,
        client: Any,
        table_name: str,
        clock: Callable[[], float] = time.time,
        lease_token_factory: Callable[[], str] | None = None,
    ) -> None:
        if not table_name:
            raise ValueError("table_name must not be empty")

        self.client = client
        self.table_name = table_name
        self.clock = clock
        self.lease_token_factory = lease_token_factory or (lambda: str(uuid4()))

    async def claim(self, lease_duration: float) -> OutboxMessage | None:
        if lease_duration <= 0:
            raise ValueError("lease_duration must be positive")

        return await asyncio.to_thread(self._claim, lease_duration)

    async def confirm(self, message: OutboxMessage) -> None:
        await asyncio.to_thread(self._confirm, message)

    async def reschedule(self, message: OutboxMessage, delay: float) -> None:
        if delay < 0:
            raise ValueError("delay must not be negative")

        await asyncio.to_thread(self._reschedule, message, delay)

    def _claim(self, lease_duration: float) -> OutboxMessage | None:
        now = self.clock()

        for status in (OUTBOX_PENDING, OUTBOX_CLAIMED):
            cursor: dict[str, Any] | None = None

            while True:
                request: dict[str, Any] = {
                    "TableName": self.table_name,
                    "IndexName": OUTBOX_INDEX,
                    "KeyConditionExpression": "#status = :status AND #next_attempt <= :now",
                    "ExpressionAttributeNames": {
                        "#status": "status",
                        "#next_attempt": "nextAttemptAt",
                    },
                    "ExpressionAttributeValues": {
                        ":status": {"S": status},
                        ":now": {"N": str(now)},
                    },
                    "Limit": OUTBOX_CLAIM_LIMIT,
                }

                if cursor is not None:
                    request["ExclusiveStartKey"] = cursor

                page = self.client.query(**request)

                for item in page.get("Items", []):
                    message = self._try_claim(item, status, now, lease_duration)

                    if message is not None:
                        return message

                cursor = page.get("LastEvaluatedKey")

                if not cursor:
                    break

        return None

    def _try_claim(
        self,
        item: dict[str, Any],
        status: str,
        now: float,
        lease_duration: float,
    ) -> OutboxMessage | None:
        message_id = item.get("messageId", {}).get("S")
        due_at = item.get("nextAttemptAt", {}).get("N")

        if not message_id or due_at is None:
            raise RuntimeError("DynamoDB returned an invalid outbox record")

        lease_token = self.lease_token_factory()
        lease_until = now + lease_duration

        try:
            updated = self.client.update_item(
                TableName=self.table_name,
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
                    ":claimed": {"S": OUTBOX_CLAIMED},
                    ":lease_token": {"S": lease_token},
                    ":lease_until": {"N": str(lease_until)},
                    ":one": {"N": "1"},
                },
                ReturnValues="ALL_NEW",
            )
        except ClientError as error:
            if error.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException":
                return None

            raise

        claimed = updated.get("Attributes")

        if not isinstance(claimed, dict):
            raise RuntimeError("DynamoDB did not return the claimed outbox record")

        envelope = self._envelope(claimed)

        return OutboxMessage(
            message_id=message_id,
            envelope=json.dumps(envelope, separators=(",", ":")).encode(),
            lease_token=lease_token,
        )

    def _confirm(self, message: OutboxMessage) -> None:
        now = datetime.fromtimestamp(self.clock(), UTC).isoformat().replace("+00:00", "Z")

        try:
            self.client.update_item(
                TableName=self.table_name,
                Key={"messageId": {"S": message.message_id}},
                ConditionExpression="#status = :claimed AND #lease_token = :lease_token AND #next_attempt > :lease_now",
                UpdateExpression="SET #status = :published, #published_at = :now REMOVE #lease_token",
                ExpressionAttributeNames={
                    "#status": "status",
                    "#lease_token": "leaseToken",
                    "#published_at": "publishedAt",
                    "#next_attempt": "nextAttemptAt",
                },
                ExpressionAttributeValues={
                    ":claimed": {"S": OUTBOX_CLAIMED},
                    ":lease_token": {"S": message.lease_token},
                    ":published": {"S": OUTBOX_PUBLISHED},
                    ":now": {"S": now},
                    ":lease_now": {"N": str(self.clock())},
                },
            )
        except ClientError as error:
            if error.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException":
                raise OutboxLeaseLostError("outbox message lease is no longer owned") from error

            raise

    def _reschedule(self, message: OutboxMessage, delay: float) -> None:
        next_attempt_at = self.clock() + delay

        try:
            self.client.update_item(
                TableName=self.table_name,
                Key={"messageId": {"S": message.message_id}},
                ConditionExpression="#status = :claimed AND #lease_token = :lease_token AND #next_attempt > :now",
                UpdateExpression="SET #status = :pending, #next_attempt = :next_attempt REMOVE #lease_token",
                ExpressionAttributeNames={
                    "#status": "status",
                    "#lease_token": "leaseToken",
                    "#next_attempt": "nextAttemptAt",
                },
                ExpressionAttributeValues={
                    ":claimed": {"S": OUTBOX_CLAIMED},
                    ":lease_token": {"S": message.lease_token},
                    ":pending": {"S": OUTBOX_PENDING},
                    ":next_attempt": {"N": str(next_attempt_at)},
                    ":now": {"N": str(self.clock())},
                },
            )
        except ClientError as error:
            if error.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException":
                raise OutboxLeaseLostError("outbox message lease is no longer owned") from error

            raise

    @classmethod
    def _envelope(cls, item: dict[str, Any]) -> dict[str, Any]:
        return {
            "messageId": cls._string(item, "messageId"),
            "correlationId": cls._string(item, "correlationId"),
            "type": cls._string(item, "type"),
            "version": cls._number(item, "version"),
            "occurredAt": cls._string(item, "occurredAt"),
            "payload": cls._value(item.get("payload", {})),
        }

    @staticmethod
    def _string(item: dict[str, Any], key: str) -> str:
        value = item.get(key, {}).get("S")

        if not isinstance(value, str):
            raise RuntimeError(f"DynamoDB outbox record has an invalid {key}")

        return value

    @staticmethod
    def _number(item: dict[str, Any], key: str) -> int | float:
        value = item.get(key, {}).get("N")

        if value is None:
            raise RuntimeError(f"DynamoDB outbox record has an invalid {key}")

        number = float(value)

        return int(number) if number.is_integer() else number

    @classmethod
    def _value(cls, attribute: dict[str, Any]) -> Any:
        if "S" in attribute:
            return attribute["S"]

        if "N" in attribute:
            number = float(attribute["N"])
            return int(number) if number.is_integer() else number

        if "BOOL" in attribute:
            return attribute["BOOL"]

        if "NULL" in attribute:
            return None

        if "M" in attribute:
            return {key: cls._value(value) for key, value in attribute["M"].items()}

        if "L" in attribute:
            return [cls._value(value) for value in attribute["L"]]

        raise RuntimeError("DynamoDB outbox record contains an unsupported attribute type")
