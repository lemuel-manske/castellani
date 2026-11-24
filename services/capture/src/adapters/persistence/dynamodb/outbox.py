import asyncio
import json
import time
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any, cast
from uuid import uuid4

from botocore.exceptions import ClientError

from domain import OutboxMessage, OutboxRepository
from tables import OUTBOX_TABLE

from .queries.outbox import (
    claim_message,
    confirm_message,
    message_from_item,
    query_due_messages,
    reschedule_message,
)

OUTBOX_PENDING = "PENDING"
OUTBOX_CLAIMED = "CLAIMED"
OUTBOX_PUBLISHED = "PUBLISHED"


def new_lease_token() -> str:
    return str(uuid4())


class OutboxLeaseLostError(RuntimeError):
    """Raised when an outbox message is no longer owned by this dispatcher."""


class DynamoDBOutbox(OutboxRepository):
    """Claims due outbox records and records their publication outcome."""

    def __init__(
        self,
        client: Any,
        clock: Callable[[], float] = time.time,
        lease_token_factory: Callable[[], str] = new_lease_token,
    ) -> None:
        self.client = client

        self.clock = clock

        self.lease_token_factory = lease_token_factory

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
                page = query_due_messages(
                    self.client,
                    OUTBOX_TABLE,
                    status,
                    now,
                    cursor,
                )

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
            updated = claim_message(
                self.client,
                OUTBOX_TABLE,
                message_id,
                status,
                OUTBOX_CLAIMED,
                due_at,
                lease_token,
                lease_until,
            )
        except ClientError as error:
            if error.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException":
                return None

            raise

        claimed = updated.get("Attributes")

        if not isinstance(claimed, dict):
            raise RuntimeError("DynamoDB did not return the claimed outbox record")

        envelope = message_from_item(cast(dict[str, Any], claimed))

        return OutboxMessage(
            message_id=message_id,
            envelope=json.dumps(envelope, separators=(",", ":")).encode(),
            lease_token=lease_token,
        )

    def _confirm(self, message: OutboxMessage) -> None:
        published_at = datetime.fromtimestamp(self.clock(), UTC).isoformat().replace("+00:00", "Z")

        try:
            confirm_message(
                self.client,
                OUTBOX_TABLE,
                message.message_id,
                message.lease_token,
                OUTBOX_CLAIMED,
                OUTBOX_PUBLISHED,
                published_at,
                self.clock(),
            )
        except ClientError as error:
            if error.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException":
                raise OutboxLeaseLostError("outbox message lease is no longer owned") from error

            raise

    def _reschedule(self, message: OutboxMessage, delay: float) -> None:
        next_attempt_at = self.clock() + delay

        try:
            reschedule_message(
                self.client,
                OUTBOX_TABLE,
                message.message_id,
                message.lease_token,
                OUTBOX_CLAIMED,
                OUTBOX_PENDING,
                next_attempt_at,
                self.clock(),
            )
        except ClientError as error:
            if error.response.get("Error", {}).get("Code") == "ConditionalCheckFailedException":
                raise OutboxLeaseLostError("outbox message lease is no longer owned") from error

            raise
