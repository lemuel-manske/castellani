import asyncio
import time
from collections.abc import Callable
from typing import Any
from uuid import NAMESPACE_URL, uuid4, uuid5

from botocore.exceptions import ClientError

from domain.capture import (
    CaptureOutcome,
    DiscoveredPage,
    TaskClaim,
    TaskRepository,
    identify_discovered_pages,
    new_attempt_id,
)

from .error_handling import (
    extract_cancellation_reasons,
    is_conditional_failure,
    is_transaction_canceled,
)
from .queries.task import (
    admit_page_transaction,
    claim_from_item,
    claim_task_transaction,
    complete_task_transaction,
    finish_task,
    is_page_captured_message,
    is_release_message,
    read_frontier,
    read_outbox,
    read_run,
    release_task_transaction,
    renew_task_transaction,
)
from .values import number_from_item


class TaskClaimLostError(RuntimeError):
    """Raised when a worker no longer owns the current page-task attempt."""


class ConditionalWriteRejected(RuntimeError):
    """Raised when a DynamoDB transaction is rejected due to a conditional failure."""


class DynamoDBTaskRepository(TaskRepository):
    """Acquires and renews fenced page-task claims against the Capture frontier."""

    def __init__(
        self,
        client: Any,
        lease_duration: float,
        clock: Callable[[], float] = time.time,
    ) -> None:
        if lease_duration <= 0:
            raise ValueError("lease_duration must be positive")

        self.client = client

        self.lease_duration = lease_duration

        self.clock = clock

    async def claim(self, archive_id: str, url_key: str) -> TaskClaim | None:
        attempt_id = new_attempt_id()

        return await asyncio.to_thread(self._claim, archive_id, url_key, attempt_id)

    async def renew(self, claim: TaskClaim) -> TaskClaim:
        return await asyncio.to_thread(self._renew, claim)

    async def complete(self, outcome: CaptureOutcome) -> None:
        await asyncio.to_thread(self._complete, outcome)

    async def fail(self, claim: TaskClaim, reason_code: str, message: str) -> None:
        await asyncio.to_thread(self._fail, claim, reason_code, message)

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

        run = read_run(self.client, claim.task.archive_id)

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
        archive_id = claim.task.archive_id
        url_key = page.identity.url_key

        transaction = admit_page_transaction(
            claim,
            page,
            message_id,
            now,
        )

        try:
            self._transact(transaction, None)
            return True
        except ConditionalWriteRejected as error:
            existing = read_frontier(
                self.client,
                archive_id,
                url_key,
            )

            if existing is not None:
                stored_identity = existing.get("navigationUrl", {}).get("S")

                if stored_identity != page.identity.navigation_url:
                    raise RuntimeError(
                        "URL identity hash collision: stored navigation identity differs"
                    ) from error

                return True

            parent = read_frontier(
                self.client,
                archive_id,
                claim.task.url_key,
            )

            if (
                parent is None
                or parent.get("state", {}).get("S") != "CLAIMED"
                or parent.get("attemptId", {}).get("S") != claim.attempt_id
                or parent.get("fence", {}).get("N") != str(claim.fence)
                or float(parent.get("leaseUntil", {}).get("N", "0")) <= now
            ):
                raise TaskClaimLostError("parent page-task claim is no longer owned") from error

            run = read_run(self.client, archive_id)

            if run is None:
                raise RuntimeError("Capture run disappeared during discovery admission") from error

            if run.get("admission", {}).get("S") != "OPEN":
                raise TaskClaimLostError("Capture run admission is closed") from error

            maximum = number_from_item(run, "maxPages", "capture run")
            admitted = number_from_item(run, "admittedPages", "capture run", default=0)

            if admitted >= maximum:
                return False

            raise

    def _complete(self, outcome: CaptureOutcome) -> None:
        now = self.clock()
        message_id = str(
            uuid5(
                NAMESPACE_URL,
                f"page-captured:{outcome.archive_id}:{outcome.snapshot_id}",
            )
        )
        depth = self._task_depth(outcome.archive_id, outcome.url_key)

        transaction = complete_task_transaction(
            outcome,
            depth,
            message_id,
            now,
        )

        try:
            self._transact(transaction, None)
        except ConditionalWriteRejected as error:
            existing = read_frontier(
                self.client,
                outcome.archive_id,
                outcome.url_key,
            )

            if (
                existing is not None
                and existing.get("state", {}).get("S") == "COMPLETED"
                and existing.get("snapshotId", {}).get("S") == outcome.snapshot_id
            ):
                event = read_outbox(
                    self.client,
                    message_id,
                )

                if event is not None and is_page_captured_message(
                    event, outcome.archive_id, outcome.snapshot_id
                ):
                    return

            raise TaskClaimLostError("page-task claim is no longer completable") from error

    def _task_depth(self, archive_id: str, url_key: str) -> int:
        item = read_frontier(
            self.client,
            archive_id,
            url_key,
        )

        if item is None:
            raise RuntimeError("page-task disappeared before completion")

        return int(item.get("depth", {}).get("N", "0"))

    def _fail(self, claim: TaskClaim, reason_code: str, message: str) -> None:
        self._finish(
            archive_id=claim.task.archive_id,
            url_key=claim.task.url_key,
            attempt_id=claim.attempt_id,
            fence=claim.fence,
            state="FAILED",
            reason_code=reason_code,
            message=message,
        )

    def _finish(
        self,
        archive_id: str,
        url_key: str,
        attempt_id: str,
        fence: int,
        state: str,
        reason_code: str | None = None,
        message: str | None = None,
    ) -> None:
        try:
            finish_task(
                self.client,
                archive_id,
                url_key,
                attempt_id,
                fence,
                state,
                reason_code,
                message,
                self.clock(),
            )
        except ClientError as error:
            if is_conditional_failure(error) or is_transaction_canceled(error):
                raise TaskClaimLostError("page-task claim is no longer owned") from error

            raise

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

        transaction = release_task_transaction(
            claim,
            message_id,
            now,
        )

        try:
            self._transact(transaction, None)
        except ConditionalWriteRejected as error:
            existing = read_outbox(
                self.client,
                message_id,
            )

            if existing is None:
                raise TaskClaimLostError("page-task claim is no longer releasable") from error

            if not is_release_message(existing, claim):
                raise RuntimeError("CapturePage outbox message identity collision") from error

    def _claim(self, archive_id: str, url_key: str, attempt_id: str) -> TaskClaim | None:
        now = self.clock()
        lease_until = now + self.lease_duration

        transaction = claim_task_transaction(
            archive_id,
            url_key,
            attempt_id,
            lease_until,
            now,
        )

        try:
            self._transact(transaction, str(uuid4()))
        except ConditionalWriteRejected:
            return None

        item = read_frontier(
            self.client,
            archive_id,
            url_key,
        )

        if item is None or item.get("attemptId", {}).get("S") != attempt_id:
            return None

        return claim_from_item(archive_id, url_key, item)

    def _renew(self, claim: TaskClaim) -> TaskClaim:
        now = self.clock()
        lease_until = now + self.lease_duration
        request_token = str(uuid4())

        transaction = renew_task_transaction(
            claim.task.archive_id,
            claim.task.url_key,
            claim.attempt_id,
            claim.fence,
            lease_until,
            now,
        )

        try:
            self._transact(transaction, request_token)
        except ConditionalWriteRejected as error:
            raise TaskClaimLostError("page-task claim is no longer owned") from error

        item = read_frontier(
            self.client,
            claim.task.archive_id,
            claim.task.url_key,
        )

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
