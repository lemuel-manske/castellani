import asyncio
import time
from collections.abc import Callable
from typing import Any
from uuid import NAMESPACE_URL, uuid4, uuid5

from botocore.exceptions import ClientError

from adapters.persistence.dynamodb.error_handling import (
    extract_cancellation_reasons,
    is_transaction_canceled,
)
from domain.task import PageTask, TaskClaim


def new_attempt_id() -> str:
    return str(uuid4())


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


class TaskClaimLostError(RuntimeError):
    """Raised when a worker no longer owns the current page-task attempt."""


class ConditionalWriteRejected(RuntimeError):
    pass


class DynamoDBTaskClaims:
    """Acquires and renews fenced page-task claims against the Capture frontier."""

    def __init__(
        self,
        client: Any,
        frontier_table_name: str,
        runs_table_name: str,
        lease_duration: float,
        clock: Callable[[], float] = time.time,
        attempt_id_factory: Callable[[], str] = new_attempt_id,
    ) -> None:
        if not frontier_table_name:
            raise ValueError("frontier_table_name must not be empty")

        if not runs_table_name:
            raise ValueError("runs_table_name must not be empty")

        if lease_duration <= 0:
            raise ValueError("lease_duration must be positive")

        self.client = client
        self.frontier_table_name = frontier_table_name
        self.runs_table_name = runs_table_name
        self.lease_duration = lease_duration

        self.clock = clock
        self.attempt_id_factory = attempt_id_factory

    async def claim(self, archive_id: str, url_key: str) -> TaskClaim | None:
        if not archive_id:
            raise ValueError("archive_id must not be empty")

        if not url_key:
            raise ValueError("url_key must not be empty")

        attempt_id = self.attempt_id_factory()

        if not attempt_id:
            raise ValueError("attempt_id_factory returned an empty value")

        return await asyncio.to_thread(self._claim, archive_id, url_key, attempt_id)

    async def renew(self, claim: TaskClaim) -> TaskClaim:
        return await asyncio.to_thread(self._renew, claim)

    def _claim(self, archive_id: str, url_key: str, attempt_id: str) -> TaskClaim | None:
        now = self.clock()
        lease_until = now + self.lease_duration

        transaction = [
            {
                "ConditionCheck": {
                    "TableName": self.runs_table_name,
                    "Key": {"archiveId": {"S": archive_id}},
                    "ConditionExpression": "#admission = :open",
                    "ExpressionAttributeNames": {"#admission": "admission"},
                    "ExpressionAttributeValues": {":open": {"S": "OPEN"}},
                }
            },
            {
                "Update": {
                    "TableName": self.frontier_table_name,
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

        try:
            self._transact(transaction, str(uuid5(NAMESPACE_URL, attempt_id)))
        except ConditionalWriteRejected:
            return None

        item = self._read_frontier(archive_id, url_key)

        if item is None or item.get("attemptId", {}).get("S") != attempt_id:
            return None

        return claim_from_item(archive_id, url_key, item)

    def _renew(self, claim: TaskClaim) -> TaskClaim:
        now = self.clock()
        lease_until = now + self.lease_duration

        request_token = str(
            uuid5(
                NAMESPACE_URL,
                f"{claim.attempt_id}:{claim.fence}:{lease_until}",
            )
        )

        transaction = [
            {
                "ConditionCheck": {
                    "TableName": self.runs_table_name,
                    "Key": {"archiveId": {"S": claim.task.archive_id}},
                    "ConditionExpression": "#admission = :open",
                    "ExpressionAttributeNames": {"#admission": "admission"},
                    "ExpressionAttributeValues": {":open": {"S": "OPEN"}},
                }
            },
            {
                "Update": {
                    "TableName": self.frontier_table_name,
                    "Key": {
                        "archiveId": {"S": claim.task.archive_id},
                        "urlKey": {"S": claim.task.url_key},
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
                        ":attempt": {"S": claim.attempt_id},
                        ":fence": {"N": str(claim.fence)},
                        ":lease": {"N": str(lease_until)},
                        ":now": {"N": str(now)},
                    },
                }
            },
        ]

        try:
            self._transact(transaction, request_token)
        except ConditionalWriteRejected as error:
            raise TaskClaimLostError("page-task claim is no longer owned") from error

        item = self._read_frontier(claim.task.archive_id, claim.task.url_key)

        if item is None:
            raise TaskClaimLostError("page-task disappeared after lease renewal")

        renewed = claim_from_item(
            claim.task.archive_id,
            claim.task.url_key,
            item,
        )

        if renewed.attempt_id != claim.attempt_id or renewed.fence != claim.fence:
            raise TaskClaimLostError("page-task ownership changed after lease renewal")

        return renewed

    def _transact(self, items: list[dict[str, Any]], request_token: str) -> None:
        for attempt in range(5):
            try:
                self.client.transact_write_items(
                    TransactItems=items,
                    ClientRequestToken=request_token,
                )
                return
            except ClientError as error:
                if is_transaction_canceled(error):
                    raise

                codes = extract_cancellation_reasons(error)

                if "ConditionalCheckFailed" in codes:
                    raise ConditionalWriteRejected from error

                if "TransactionConflict" not in codes or attempt == 4:
                    raise

                time.sleep(0.01 * (2**attempt))

    def _read_frontier(self, archive_id: str, url_key: str) -> dict[str, Any] | None:
        response = self.client.get_item(
            TableName=self.frontier_table_name,
            Key={
                "archiveId": {"S": archive_id},
                "urlKey": {"S": url_key},
            },
            ConsistentRead=True,
        )

        item = response.get("Item")

        return item if item else None
