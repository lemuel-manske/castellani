import asyncio
import time
from typing import Any

from botocore.exceptions import ClientError

from adapters.serialization import artifact_document
from domain.capture import (
    ADMISSION_CLOSED,
    MANIFEST_PENDING,
    CaptureRunMissing,
    ManifestFinalization,
    ManifestSource,
    manifest_message_id,
)
from ports.capture import ArchiveFinalizationRepository
from ports.clock import Clock

from .error_handling import ConditionalWriteRejected, raise_unless_transaction_canceled
from .queries.finalize import (
    finalize_transaction,
    is_crawl_completed_message,
    is_published_manifest,
    manifest_source,
    plain_attributes,
    query_frontier,
    query_snapshots,
)
from .queries.task import read_outbox, read_run
from .values import optional_string


class DynamoDBArchiveFinalizationRepository(ArchiveFinalizationRepository):
    """Reads and commits the durable facts of a crawl manifest."""

    def __init__(
        self,
        client: Any,
        clock: Clock = time.time,
    ) -> None:
        self.client = client
        self.clock = clock

    async def read_manifest_source(self, archive_id: str) -> ManifestSource | None:
        def read() -> ManifestSource | None:
            run = read_run(self.client, archive_id)

            if run is None:
                raise CaptureRunMissing("Capture run disappeared during finalization")

            if (
                optional_string(run, "admission") != ADMISSION_CLOSED
                or optional_string(run, "manifestStatus") != MANIFEST_PENDING
            ):
                return None

            return manifest_source(
                plain_attributes(run),
                query_snapshots(self.client, archive_id),
                query_frontier(self.client, archive_id),
            )

        return await asyncio.to_thread(read)

    async def commit_manifest(self, finalization: ManifestFinalization) -> None:
        def commit() -> None:
            transaction = finalize_transaction(
                archive_id=finalization.archive_id,
                artifact=artifact_document(finalization.artifact),
                digest=finalization.digest,
                occurred_at=finalization.occurred_at,
                message_id=manifest_message_id(finalization.archive_id),
                now=self.clock(),
                seed_ok=finalization.seed_succeeded,
                captured_count=finalization.captured_count,
                failed_count=finalization.failed_count,
            )

            try:
                self.client.transact_write_items(TransactItems=transaction)
            except ClientError as error:
                raise_unless_transaction_canceled(error)

                current = read_run(self.client, finalization.archive_id)

                if current is not None and is_published_manifest(current, finalization.digest):
                    existing = read_outbox(
                        self.client,
                        manifest_message_id(finalization.archive_id),
                    )

                    if existing is not None and is_crawl_completed_message(
                        existing,
                        finalization.archive_id,
                        finalization.digest,
                    ):
                        return

                raise ConditionalWriteRejected from error

        await asyncio.to_thread(commit)
