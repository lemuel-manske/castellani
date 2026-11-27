import asyncio
import time
from dataclasses import replace
from typing import Any
from uuid import uuid4

from botocore.exceptions import ClientError

from domain.capture import (
    CompensationDecision,
    InvalidArchiveDecision,
    InvalidLeaseDuration,
    PackageCommitRejected,
    PendingPackage,
    PreparedPackage,
    PublicationDecision,
    archive_compensated_message_id,
    archive_prepared_message_id,
    archive_published_message_id,
)
from ports.capture import ArchivePublicationRepository
from ports.clock import Clock

from .error_handling import (
    ConditionalWriteRejected,
    is_conditional_failure,
    is_transaction_canceled,
)
from .queries.publication import (
    begin_compensation as begin_compensation_query,
)
from .queries.publication import (
    claim_package as claim_package_query,
)
from .queries.publication import (
    complete_compensation as complete_compensation_query,
)
from .queries.publication import (
    is_compensated_message,
    is_compensating_decision,
    is_prepared_message,
    is_prepared_package,
    is_published_decision,
    is_published_message,
    pending_package_from_item,
    scan_pending_packages,
)
from .queries.publication import (
    prepare_package as prepare_package_query,
)
from .queries.publication import (
    publish_package as publish_package_query,
)
from .queries.publication import (
    release_package as release_package_query,
)
from .queries.task import read_outbox, read_run


class DynamoDBArchivePublicationRepository(ArchivePublicationRepository):
    """Durable run state for WACZ preparation and Coordinator decisions."""

    def __init__(
        self,
        client: Any,
        clock: Clock = time.time,
    ) -> None:
        self.client = client
        self.clock = clock

    async def claim_package(self, lease_duration: float) -> PendingPackage | None:
        if lease_duration <= 0:
            raise InvalidLeaseDuration("lease_duration must be positive")

        def claim() -> PendingPackage | None:
            now = self.clock()
            lease_until = now + lease_duration
            owner = str(uuid4())
            cursor: dict[str, Any] | None = None

            while True:
                page = scan_pending_packages(self.client, now, cursor)

                for item in page.get("Items", ()):
                    pending = pending_package_from_item(item)

                    try:
                        claim_package_query(
                            self.client,
                            pending.archive_id,
                            now,
                            lease_until,
                            owner,
                        )
                    except ClientError as error:
                        if not is_conditional_failure(error):
                            raise

                        continue

                    return replace(pending, lease_owner=owner)

                cursor = page.get("LastEvaluatedKey")

                if not cursor:
                    return None

        return await asyncio.to_thread(claim)

    async def release_package(self, pending: PendingPackage) -> None:
        def release() -> None:
            try:
                release_package_query(self.client, pending.archive_id, pending.lease_owner)
            except ClientError as error:
                if not is_conditional_failure(error):
                    raise

        await asyncio.to_thread(release)

    async def prepare(self, prepared: PreparedPackage) -> None:
        def commit() -> None:
            message_id = archive_prepared_message_id(
                prepared.archive_id,
                prepared.manifest_digest,
            )

            try:
                prepare_package_query(
                    self.client,
                    prepared,
                    message_id,
                    prepared.occurred_at,
                    self.clock(),
                )
            except ClientError as error:
                if not is_transaction_canceled(error):
                    raise

                current = read_run(self.client, prepared.archive_id)
                outbox = read_outbox(self.client, message_id)

                if (
                    current is not None
                    and is_prepared_package(current, prepared)
                    and outbox is not None
                    and is_prepared_message(outbox, prepared.archive_id, prepared.artifact.sha256)
                ):
                    return

                raise PackageCommitRejected from error

        await asyncio.to_thread(commit)

    async def accept_publication(self, decision: PublicationDecision) -> None:
        def accept() -> None:
            message_id = archive_published_message_id(
                decision.archive_id, decision.decision_version
            )

            try:
                publish_package_query(self.client, decision, message_id, self.clock())
            except ClientError as error:
                if not is_transaction_canceled(error):
                    raise

                current = read_run(self.client, decision.archive_id)
                outbox = read_outbox(self.client, message_id)

                if (
                    current is not None
                    and is_published_decision(current, decision)
                    and outbox is not None
                    and is_published_message(outbox, decision)
                ):
                    return

                raise InvalidArchiveDecision(
                    "publication decision conflicts with local package facts"
                ) from error

        await asyncio.to_thread(accept)

    async def begin_compensation(self, decision: CompensationDecision) -> None:
        def begin() -> None:
            try:
                begin_compensation_query(self.client, decision)
            except ClientError as error:
                if not is_conditional_failure(error):
                    raise

                current = read_run(self.client, decision.archive_id)

                if current is not None and is_compensating_decision(current, decision):
                    return

                raise InvalidArchiveDecision(
                    "compensation decision conflicts with an existing decision"
                ) from error

        await asyncio.to_thread(begin)

    async def complete_compensation(self, decision: CompensationDecision) -> None:
        def complete() -> None:
            message_id = archive_compensated_message_id(
                decision.archive_id, decision.decision_version
            )

            try:
                complete_compensation_query(self.client, decision, message_id, self.clock())
            except ClientError as error:
                if not is_transaction_canceled(error):
                    raise

                outbox = read_outbox(self.client, message_id)

                if outbox is not None and is_compensated_message(outbox, decision):
                    return

                raise ConditionalWriteRejected from error

        await asyncio.to_thread(complete)
