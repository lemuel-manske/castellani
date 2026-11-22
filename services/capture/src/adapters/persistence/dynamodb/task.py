import asyncio
import time
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any
from uuid import NAMESPACE_URL, uuid4, uuid5

from botocore.exceptions import ClientError

from domain import (
    ArtifactReference,
    CaptureOutcome,
    DiscoveredPage,
    PageTask,
    TaskClaim,
    TaskRepository,
    identify_discovered_pages,
    new_attempt_id,
)

from .error_handling import (
    extract_cancellation_reasons,
    is_transaction_canceled,
)
from .values import number_from_item


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
    """Raised when a DynamoDB transaction is rejected due to a conditional failure."""


class DynamoDBTaskRepository(TaskRepository):
    """Acquires and renews fenced page-task claims against the Capture frontier."""

    def __init__(
        self,
        client: Any,
        frontier_table_name: str,
        runs_table_name: str,
        lease_duration: float,
        clock: Callable[[], float] = time.time,
        outbox_table_name: str = "capture_outbox",
        snapshots_table_name: str = "capture_snapshots",
        max_attempts: int = 3,
        retry_base_delay: float = 30,
    ) -> None:
        if not frontier_table_name:
            raise ValueError("frontier_table_name must not be empty")

        if not runs_table_name:
            raise ValueError("runs_table_name must not be empty")

        if not snapshots_table_name:
            raise ValueError("snapshots_table_name must not be empty")

        if not outbox_table_name:
            raise ValueError("outbox_table_name must not be empty")

        if lease_duration <= 0:
            raise ValueError("lease_duration must be positive")

        if max_attempts < 1:
            raise ValueError("max_attempts must be positive")

        if retry_base_delay <= 0:
            raise ValueError("retry_base_delay must be positive")

        self.client = client
        self.frontier_table_name = frontier_table_name
        self.runs_table_name = runs_table_name
        self.snapshots_table_name = snapshots_table_name
        self.outbox_table_name = outbox_table_name
        self.lease_duration = lease_duration
        self.max_attempts = max_attempts
        self.retry_base_delay = retry_base_delay

        self.clock = clock

    async def claim(self, archive_id: str, url_key: str) -> TaskClaim | None:
        if not archive_id:
            raise ValueError("archive_id must not be empty")

        if not url_key:
            raise ValueError("url_key must not be empty")

        attempt_id = new_attempt_id()

        return await asyncio.to_thread(self._claim, archive_id, url_key, attempt_id)

    async def renew(self, claim: TaskClaim) -> TaskClaim:
        return await asyncio.to_thread(self._renew, claim)

    async def complete(self, outcome: CaptureOutcome) -> None:
        await asyncio.to_thread(self._complete, outcome)

    async def fail(
        self,
        claim: TaskClaim,
        reason_code: str,
        message: str,
        retryable: bool = True,
    ) -> None:
        await asyncio.to_thread(self._fail, claim, reason_code, message, retryable)

    async def admit_discovered(
        self,
        claim: TaskClaim,
        discovered_urls: tuple[str, ...],
    ) -> None:
        pages = identify_discovered_pages(claim.task, discovered_urls)
        await asyncio.to_thread(self._admit_discovered, claim, pages)

    async def release(self, claim: TaskClaim) -> None:
        await asyncio.to_thread(self._release, claim)

    def _admit_discovered(self, claim: TaskClaim, pages: tuple[DiscoveredPage, ...]) -> None:
        if not pages:
            return

        run = self._read_run(claim.task.archive_id)
        if run is None:
            raise RuntimeError("Capture run does not exist")
        if run.get("admission", {}).get("S") != "OPEN":
            raise TaskClaimLostError("Capture run admission is closed")

        maximum = number_from_item(run, "maxPages", "capture run")
        admitted = number_from_item(run, "admittedPages", "capture run")

        if admitted >= maximum:
            return

        for page in pages:
            if page.identity.url_key == claim.task.url_key:
                continue

            if not self._admit_discovered_page(claim, page):
                return

    def _admit_discovered_page(self, claim: TaskClaim, page: DiscoveredPage) -> bool:
        now = self.clock()
        message_id = str(
            uuid5(
                NAMESPACE_URL,
                f"capture-page:{claim.task.archive_id}:{page.identity.url_key}",
            )
        )
        occurred_at = datetime.fromtimestamp(now, UTC).isoformat().replace("+00:00", "Z")
        archive_id = claim.task.archive_id
        url_key = page.identity.url_key

        transaction = [
            {
                "ConditionCheck": {
                    "TableName": self.frontier_table_name,
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
                    "TableName": self.runs_table_name,
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
                    "TableName": self.frontier_table_name,
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
                    "TableName": self.outbox_table_name,
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

        try:
            self._transact(transaction, None)
            return True
        except ConditionalWriteRejected as error:
            existing = self._read_frontier(archive_id, url_key)

            if existing is not None:
                stored_identity = existing.get("navigationUrl", {}).get("S")
                if stored_identity != page.identity.navigation_url:
                    raise RuntimeError(
                        "URL identity hash collision: stored navigation identity differs"
                    ) from error
                return True

            parent = self._read_frontier(archive_id, claim.task.url_key)
            if (
                parent is None
                or parent.get("state", {}).get("S") != "CLAIMED"
                or parent.get("attemptId", {}).get("S") != claim.attempt_id
                or parent.get("fence", {}).get("N") != str(claim.fence)
                or float(parent.get("leaseUntil", {}).get("N", "0")) <= now
            ):
                raise TaskClaimLostError("parent page-task claim is no longer owned") from error

            run = self._read_run(archive_id)
            if run is None:
                raise RuntimeError("Capture run disappeared during discovery admission") from error

            if run.get("admission", {}).get("S") != "OPEN":
                raise TaskClaimLostError("Capture run admission is closed") from error

            maximum = number_from_item(run, "maxPages", "capture run")
            admitted = number_from_item(run, "admittedPages", "capture run", default=0)

            if admitted >= maximum:
                return False

            # The failed condition was not a duplicate or a full run. Re-raise
            # rather than silently dropping a discovery on an unexpected conflict.
            raise

    def _read_run(self, archive_id: str) -> dict[str, Any] | None:
        response = self.client.get_item(
            TableName=self.runs_table_name,
            Key={"archiveId": {"S": archive_id}},
            ConsistentRead=True,
        )
        item = response.get("Item")
        return item if item else None

    def _complete(self, outcome: CaptureOutcome) -> None:
        now = self.clock()
        occurred_at = datetime.fromtimestamp(now, UTC).isoformat().replace("+00:00", "Z")
        captured_at = outcome.capture.captured_at
        if captured_at.tzinfo is None:
            captured_at = captured_at.replace(tzinfo=UTC)
        captured_at_text = captured_at.astimezone(UTC).isoformat().replace("+00:00", "Z")
        message_id = str(
            uuid5(
                NAMESPACE_URL,
                f"page-captured:{outcome.archive_id}:{outcome.snapshot_id}",
            )
        )
        artifacts = [self._artifact_attribute(item) for item in outcome.warc_artifacts]
        depth = self._task_depth(outcome.archive_id, outcome.url_key)
        snapshot_item: dict[str, Any] = {
            "snapshotId": {"S": outcome.snapshot_id},
            "archiveId": {"S": outcome.archive_id},
            "urlKey": {"S": outcome.url_key},
            "url": {"S": outcome.capture.requested_url},
            "finalUrl": {"S": outcome.capture.final_url},
            "capturedAt": {"S": captured_at_text},
            "minDepth": {"N": str(depth)},
            "redirectChain": {"L": [{"S": url} for url in outcome.capture.redirect_chain]},
            "warcArtifacts": {"L": artifacts},
        }
        if outcome.capture.content_type is not None:
            snapshot_item["contentType"] = {"S": outcome.capture.content_type}
        if outcome.capture.title:
            snapshot_item["title"] = {"S": outcome.capture.title}
        if outcome.capture.status_code is not None:
            snapshot_item["statusCode"] = {"N": str(outcome.capture.status_code)}
        payload: dict[str, Any] = {
            "archiveId": {"S": outcome.archive_id},
            "snapshotId": {"S": outcome.snapshot_id},
            "urlKey": {"S": outcome.url_key},
            "url": {"S": outcome.capture.requested_url},
            "finalUrl": {"S": outcome.capture.final_url},
            "redirectChain": {"L": [{"S": url} for url in outcome.capture.redirect_chain]},
            "capturedAt": {"S": captured_at_text},
            "warcArtifacts": {"L": artifacts},
        }
        if outcome.capture.content_type is not None:
            payload["contentType"] = {"S": outcome.capture.content_type}

        transaction = [
            {
                "Update": {
                    "TableName": self.frontier_table_name,
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
                        ":capture_url": {"S": outcome.capture.requested_url},
                        ":final_url": {"S": outcome.capture.final_url},
                        ":captured_at": {"S": captured_at_text},
                        ":redirects": {"L": [{"S": url} for url in outcome.capture.redirect_chain]},
                        ":artifacts": {"L": artifacts},
                        ":min_depth": {"N": str(depth)},
                    },
                }
            },
            {
                "Update": {
                    "TableName": self.runs_table_name,
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
                    "TableName": self.snapshots_table_name,
                    "Item": snapshot_item,
                    "ConditionExpression": "attribute_not_exists(#snapshot_id)",
                    "ExpressionAttributeNames": {"#snapshot_id": "snapshotId"},
                }
            },
            {
                "Put": {
                    "TableName": self.outbox_table_name,
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

        try:
            self._transact(transaction, None)
        except ConditionalWriteRejected as error:
            existing = self._read_frontier(outcome.archive_id, outcome.url_key)
            if (
                existing is not None
                and existing.get("state", {}).get("S") == "COMPLETED"
                and existing.get("snapshotId", {}).get("S") == outcome.snapshot_id
            ):
                event = self._read_outbox(message_id)
                if event is not None and self._is_page_captured_message(
                    event, outcome.archive_id, outcome.snapshot_id
                ):
                    return
            raise TaskClaimLostError("page-task claim is no longer completable") from error

    @staticmethod
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

    @staticmethod
    def _is_page_captured_message(
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

    def _task_depth(self, archive_id: str, url_key: str) -> int:
        item = self._read_frontier(archive_id, url_key)
        if item is None:
            raise RuntimeError("page-task disappeared before completion")
        return int(item.get("depth", {}).get("N", "0"))

    def _fail(
        self,
        claim: TaskClaim,
        reason_code: str,
        message: str,
        retryable: bool,
    ) -> None:
        now = self.clock()
        archive_id = claim.task.archive_id
        url_key = claim.task.url_key
        item = self._read_frontier(archive_id, url_key)

        if item is None:
            raise TaskClaimLostError("page-task claim is no longer owned")

        previous_failure_count = int(item.get("failureCount", {}).get("N", "0"))
        failure_count = previous_failure_count + 1
        retry = retryable and failure_count < self.max_attempts
        retry_at = now + self.retry_base_delay * (2 ** (failure_count - 1))
        message_id = str(
            uuid5(
                NAMESPACE_URL,
                f"capture-page-retry:{archive_id}:{url_key}:{claim.attempt_id}:{claim.fence}",
            )
        )

        # A retry of the same failure request must not enqueue another logical attempt.
        if (
            item.get("lastFailureAttemptId", {}).get("S") == claim.attempt_id
            and item.get("lastFailureFence", {}).get("N") == str(claim.fence)
        ):
            if item.get("state", {}).get("S") == "FAILED":
                return
            existing = self._read_outbox(message_id)
            if existing is not None and self._is_retry_message(existing, claim):
                return

        if (
            item.get("state", {}).get("S") != "CLAIMED"
            or item.get("attemptId", {}).get("S") != claim.attempt_id
            or item.get("fence", {}).get("N") != str(claim.fence)
            or float(item.get("leaseUntil", {}).get("N", "0")) <= now
        ):
            raise TaskClaimLostError("page-task claim is no longer owned")

        names = {
            "#state": "state",
            "#attempt": "attemptId",
            "#fence": "fence",
            "#lease": "leaseUntil",
            "#failure_count": "failureCount",
            "#reason": "failureReason",
            "#message": "failureMessage",
            "#last_attempt": "lastFailureAttemptId",
            "#last_fence": "lastFailureFence",
            "#next_attempt": "nextAttemptAt",
        }
        values: dict[str, Any] = {
            ":claimed": {"S": "CLAIMED"},
            ":attempt": {"S": claim.attempt_id},
            ":fence": {"N": str(claim.fence)},
            ":now": {"N": str(now)},
            ":previous": {"N": str(previous_failure_count)},
            ":failure_count": {"N": str(failure_count)},
            ":reason": {"S": reason_code},
            ":message": {"S": message},
            ":last_attempt": {"S": claim.attempt_id},
            ":last_fence": {"N": str(claim.fence)},
        }

        update = (
            "SET #state = :state, #failure_count = :failure_count, "
            "#reason = :reason, #message = :message, "
            "#last_attempt = :last_attempt, #last_fence = :last_fence "
            "REMOVE #attempt, #lease, #next_attempt"
        )
        if retry:
            update = (
                "SET #state = :pending, #failure_count = :failure_count, "
                "#reason = :reason, #message = :message, "
                "#last_attempt = :last_attempt, #last_fence = :last_fence, "
                "#next_attempt = :retry_at "
                "REMOVE #attempt, #lease"
            )
            values[":pending"] = {"S": "PENDING"}
            values[":retry_at"] = {"N": str(retry_at)}
        else:
            values[":state"] = {"S": "FAILED"}

        frontier_update = {
            "Update": {
                "TableName": self.frontier_table_name,
                "Key": {
                    "archiveId": {"S": archive_id},
                    "urlKey": {"S": url_key},
                },
                "UpdateExpression": update,
                "ConditionExpression": (
                    "#state = :claimed AND #attempt = :attempt "
                    "AND #fence = :fence AND #lease > :now "
                    "AND (attribute_not_exists(#failure_count) OR #failure_count = :previous)"
                ),
                "ExpressionAttributeNames": names,
                "ExpressionAttributeValues": values,
            }
        }

        if retry:
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
                frontier_update,
            ]
            occurred_at = datetime.fromtimestamp(now, UTC).isoformat().replace("+00:00", "Z")
            transaction.append(
                {
                    "Put": {
                        "TableName": self.outbox_table_name,
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
                                    "retryOfAttemptId": {"S": claim.attempt_id},
                                    "retryOfFence": {"N": str(claim.fence)},
                                }
                            },
                            "status": {"S": "PENDING"},
                            "attempts": {"N": "0"},
                            "nextAttemptAt": {"N": str(retry_at)},
                        },
                        "ConditionExpression": "attribute_not_exists(#message_id)",
                        "ExpressionAttributeNames": {"#message_id": "messageId"},
                    }
                }
            )
        else:
            transaction = [frontier_update]
            transaction.append(
                {
                    "Update": {
                        "TableName": self.runs_table_name,
                        "Key": {"archiveId": {"S": archive_id}},
                        "UpdateExpression": "ADD #outstanding :minus_one, #failed :one",
                        "ConditionExpression": "#admission = :open AND #outstanding >= :one",
                        "ExpressionAttributeNames": {
                            "#admission": "admission",
                            "#outstanding": "outstandingPages",
                            "#failed": "failedPages",
                        },
                        "ExpressionAttributeValues": {
                            ":open": {"S": "OPEN"},
                            ":minus_one": {"N": "-1"},
                            ":one": {"N": "1"},
                        },
                    }
                }
            )

        try:
            self._transact(transaction, None)
        except ConditionalWriteRejected as error:
            current = self._read_frontier(archive_id, url_key)
            same_failure = (
                current is not None
                and current.get("lastFailureAttemptId", {}).get("S") == claim.attempt_id
                and current.get("lastFailureFence", {}).get("N") == str(claim.fence)
            )

            if (
                same_failure
                and current is not None
                and current.get("state", {}).get("S") == "FAILED"
            ):
                return

            if (
                same_failure
                and current is not None
                and current.get("state", {}).get("S") == "PENDING"
            ):
                existing = self._read_outbox(message_id)
                if existing is not None and self._is_retry_message(existing, claim):
                    return

            raise TaskClaimLostError("page-task claim is no longer owned") from error

    @staticmethod
    def _is_retry_message(item: dict[str, Any], claim: TaskClaim) -> bool:
        payload = item.get("payload", {}).get("M", {})
        return (
            item.get("correlationId", {}).get("S") == claim.task.archive_id
            and item.get("type", {}).get("S") == "CapturePage"
            and payload.get("archiveId", {}).get("S") == claim.task.archive_id
            and payload.get("urlKey", {}).get("S") == claim.task.url_key
            and payload.get("retryOfAttemptId", {}).get("S") == claim.attempt_id
            and payload.get("retryOfFence", {}).get("N") == str(claim.fence)
        )

    def _release(self, claim: TaskClaim) -> None:
        now = self.clock()
        message_id = str(
            uuid5(
                NAMESPACE_URL,
                (
                    f"capture-page:{claim.task.archive_id}:{claim.task.url_key}:"
                    f"{claim.attempt_id}:{claim.fence}"
                ),
            )
        )
        occurred_at = datetime.fromtimestamp(now, UTC).isoformat().replace("+00:00", "Z")

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
                    "TableName": self.outbox_table_name,
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

        try:
            # The conditional outbox Put is the idempotency guard for release retries.
            self._transact(transaction, None)
        except ConditionalWriteRejected as error:
            existing = self._read_outbox(message_id)

            if existing is None:
                raise TaskClaimLostError("page-task claim is no longer releasable") from error

            if not self._is_release_message(existing, claim):
                raise RuntimeError("CapturePage outbox message identity collision") from error

    @staticmethod
    def _is_release_message(item: dict[str, Any], claim: TaskClaim) -> bool:
        payload = item.get("payload", {}).get("M", {})

        return (
            item.get("correlationId", {}).get("S") == claim.task.archive_id
            and item.get("type", {}).get("S") == "CapturePage"
            and payload.get("archiveId", {}).get("S") == claim.task.archive_id
            and payload.get("urlKey", {}).get("S") == claim.task.url_key
        )

    def _read_outbox(self, message_id: str) -> dict[str, Any] | None:
        response = self.client.get_item(
            TableName=self.outbox_table_name,
            Key={"messageId": {"S": message_id}},
            ConsistentRead=True,
        )

        item = response.get("Item")

        return item if item else None

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
                        "#lease = :lease, #fence = if_not_exists(#fence, :zero) + :one "
                        "REMOVE #next_attempt"
                    ),
                    "ConditionExpression": (
                        "(#state = :pending AND "
                        "(attribute_not_exists(#next_attempt) OR #next_attempt <= :now)) "
                        "OR (#state = :claimed AND #lease <= :now)"
                    ),
                    "ExpressionAttributeNames": {
                        "#state": "state",
                        "#attempt": "attemptId",
                        "#lease": "leaseUntil",
                        "#fence": "fence",
                        "#next_attempt": "nextAttemptAt",
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
            self._transact(transaction, str(uuid4()))
        except ConditionalWriteRejected:
            return None

        item = self._read_frontier(archive_id, url_key)

        if item is None or item.get("attemptId", {}).get("S") != attempt_id:
            return None

        return claim_from_item(archive_id, url_key, item)

    def _renew(self, claim: TaskClaim) -> TaskClaim:
        now = self.clock()
        lease_until = now + self.lease_duration

        request_token = str(uuid4())

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

    def _transact(
        self,
        items: list[dict[str, Any]],
        request_token: str | None,
    ) -> None:
        for attempt in range(5):
            try:
                request: dict[str, Any] = {"TransactItems": items}

                if request_token is not None:
                    request["ClientRequestToken"] = request_token

                self.client.transact_write_items(**request)

                return
            except ClientError as error:
                if not is_transaction_canceled(error):
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
