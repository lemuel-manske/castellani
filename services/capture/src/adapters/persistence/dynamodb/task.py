import asyncio
import time
from collections.abc import Awaitable, Callable
from typing import Any
from uuid import NAMESPACE_URL, uuid4, uuid5

from botocore.exceptions import ClientError

from domain.capture import (
    DEFAULT_AUTH_GENERATION,
    AuthGenerationChanged,
    CaptureOutcome,
    CaptureRunMissing,
    DiscoveredPage,
    InvalidLeaseDuration,
    TaskClaim,
    TaskClaimLostError,
    identify_discovered_pages,
    new_attempt_id,
)
from ports.capture import TaskRepository
from ports.clock import Clock

from .error_handling import (
    ConditionalWriteRejected,
    is_conditional_failure,
    is_transaction_canceled,
)
from .facilities import (
    EXPONENTIAL_BACKOFF_ATTEMPTS,
    EXPONENTIAL_BACKOFF_DELAY,
    exponential_backoff_transact,
)
from .queries.task import (
    admit_page_transaction,
    auth_generation_changed,
    claim_from_item,
    claim_task_transaction,
    closes_run,
    complete_task_transaction,
    finish_task,
    is_page_captured_message,
    is_release_message,
    read_depth,
    read_frontier,
    read_outbox,
    read_run,
    release_task_transaction,
    renew_task_transaction,
)
from .values import number_from_item


class DynamoDBTaskRepository(TaskRepository):
    """Acquires and renews fenced page-task claims against the Capture frontier."""

    def __init__(
        self,
        client: Any,
        lease_duration: float,
        clock: Clock = time.time,
        on_closed: Callable[[str], Awaitable[None]] | None = None,
    ) -> None:
        if lease_duration <= 0:
            raise InvalidLeaseDuration("lease_duration must be positive")

        self.client = client

        self.lease_duration = lease_duration

        self.clock = clock
        self.on_closed = on_closed

    async def claim(self, archive_id: str, url_key: str) -> TaskClaim | None:
        def do_claim():
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
                exponential_backoff_transact(self.client, transaction, str(uuid4()))
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

        attempt_id = new_attempt_id()

        return await asyncio.to_thread(do_claim)

    async def renew(self, claim: TaskClaim) -> TaskClaim:
        def do_renew():
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
                exponential_backoff_transact(self.client, transaction, request_token)
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

        return await asyncio.to_thread(do_renew)

    async def complete(self, outcome: CaptureOutcome) -> None:
        def do_complete() -> bool:
            message_id = str(
                uuid5(
                    NAMESPACE_URL,
                    f"page-captured:{outcome.archive_id}:{outcome.snapshot_id}",
                )
            )

            for _ in range(EXPONENTIAL_BACKOFF_ATTEMPTS):
                now = self.clock()

                depth = read_depth(self.client, outcome.archive_id, outcome.url_key)

                run = read_run(self.client, outcome.archive_id)

                if run is None:
                    raise CaptureRunMissing("Capture run disappeared during completion")

                close = closes_run(run)

                transaction = complete_task_transaction(
                    outcome,
                    depth,
                    message_id,
                    now,
                    close,
                )

                try:
                    exponential_backoff_transact(self.client, transaction, None)

                    return close
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
                            current = read_run(self.client, outcome.archive_id)

                            return (
                                current is not None
                                and current.get("admission", {}).get("S") == "CLOSED"
                            )

                    if auth_generation_changed(
                        self.client,
                        outcome.archive_id,
                        outcome.auth_generation,
                    ):
                        raise AuthGenerationChanged(
                            "authentication generation changed during capture completion"
                        ) from error

                    current = read_run(self.client, outcome.archive_id)

                    if (
                        existing is not None
                        and existing.get("state", {}).get("S") == "CLAIMED"
                        and existing.get("attemptId", {}).get("S") == outcome.attempt_id
                        and existing.get("fence", {}).get("N") == str(outcome.fence)
                        and current is not None
                        and current.get("admission", {}).get("S") == "OPEN"
                    ):
                        continue

                    raise TaskClaimLostError("page-task claim is no longer completable") from error

            raise TaskClaimLostError("page-task completion could not be committed")

        closed = await asyncio.to_thread(do_complete)

        if closed and self.on_closed is not None:
            await self.on_closed(outcome.archive_id)

    async def fail(self, claim: TaskClaim, reason_code: str, message: str) -> None:
        def do_fail() -> bool:
            for attempt in range(EXPONENTIAL_BACKOFF_ATTEMPTS):
                now = self.clock()

                run = read_run(self.client, claim.task.archive_id)

                if run is None:
                    raise CaptureRunMissing("Capture run disappeared during failure")

                close = closes_run(run)

                try:
                    finish_task(
                        self.client,
                        claim.task.archive_id,
                        claim.task.url_key,
                        claim.attempt_id,
                        claim.fence,
                        "FAILED",
                        reason_code,
                        message,
                        now,
                        close,
                    )

                    return close
                except ClientError as error:
                    if not (is_conditional_failure(error) or is_transaction_canceled(error)):
                        raise

                    existing = read_frontier(
                        self.client,
                        claim.task.archive_id,
                        claim.task.url_key,
                    )
                    current = read_run(self.client, claim.task.archive_id)

                    if (
                        existing is not None
                        and existing.get("state", {}).get("S") == "CLAIMED"
                        and existing.get("attemptId", {}).get("S") == claim.attempt_id
                        and existing.get("fence", {}).get("N") == str(claim.fence)
                        and float(existing.get("leaseUntil", {}).get("N", "0")) > now
                        and current is not None
                        and current.get("admission", {}).get("S") == "OPEN"
                    ):
                        time.sleep(EXPONENTIAL_BACKOFF_DELAY * (2**attempt))

                        continue

                    raise TaskClaimLostError("page-task claim is no longer owned") from error

            raise TaskClaimLostError("page-task failure could not be committed")

        closed = await asyncio.to_thread(do_fail)

        if closed and self.on_closed is not None:
            await self.on_closed(claim.task.archive_id)

    async def admit_discovered(
        self,
        claim: TaskClaim,
        discovered_urls: tuple[str, ...],
        auth_generation: int = DEFAULT_AUTH_GENERATION,
    ) -> None:
        def do_admit_discovered_page(page: DiscoveredPage) -> bool:
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
                auth_generation,
            )

            try:
                exponential_backoff_transact(self.client, transaction, None)

                return True
            except ConditionalWriteRejected as error:
                if auth_generation_changed(self.client, archive_id, auth_generation):
                    raise AuthGenerationChanged(
                        "authentication generation changed during discovery admission"
                    ) from error

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
                    message = "Capture run disappeared during discovery admission"

                    raise RuntimeError(message) from error

                if run.get("admission", {}).get("S") != "OPEN":
                    raise TaskClaimLostError("Capture run admission is closed") from error

                maximum = number_from_item(run, "maxPages", "capture run")
                admitted = number_from_item(run, "admittedPages", "capture run", default=0)

                if admitted >= maximum:
                    return False

                raise

        def do_admit_discovered():
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

                if not do_admit_discovered_page(page):
                    return

        pages = identify_discovered_pages(claim.task, discovered_urls)

        await asyncio.to_thread(do_admit_discovered)

    async def release(self, claim: TaskClaim) -> None:
        def do_release():
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
                exponential_backoff_transact(self.client, transaction, None)
            except ConditionalWriteRejected as error:
                existing = read_outbox(
                    self.client,
                    message_id,
                )

                if existing is None:
                    raise TaskClaimLostError("page-task claim is no longer releasable") from error

                if not is_release_message(existing, claim):
                    raise RuntimeError("CapturePage outbox message identity collision") from error

        await asyncio.to_thread(do_release)
