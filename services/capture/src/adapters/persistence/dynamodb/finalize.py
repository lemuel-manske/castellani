import asyncio
import hashlib
import json
import time
from collections.abc import Callable
from typing import Any

from botocore.exceptions import ClientError

from adapters.serialization import artifact_document, manifest_document
from domain.capture import ArtifactReference, CrawlFinalizer, manifest_key, manifest_message_id
from topology.buckets import ARCHIVE_MANIFESTS_BUCKET

from .error_handling import ConditionalWriteRejected, is_transaction_canceled
from .queries.finalize import (
    finalize_transaction,
    is_crawl_completed_message,
    is_published_manifest,
    plain_attributes,
    query_frontier,
    query_snapshots,
    seed_succeeded,
)
from .queries.task import read_outbox, read_run


class DynamoDBManifestFinalizer(CrawlFinalizer):
    """Writes the immutable crawl manifest and durable completion outbox record."""

    def __init__(
        self,
        client: Any,
        s3_client: Any,
        clock: Callable[[], float] = time.time,
    ) -> None:
        self.client = client
        self.s3_client = s3_client
        self.clock = clock

    async def __call__(self, archive_id: str) -> None:
        def finalize() -> None:
            run = read_run(self.client, archive_id)

            if run is None:
                raise RuntimeError("Capture run disappeared during finalization")

            if (
                run.get("admission", {}).get("S") != "CLOSED"
                or run.get("manifestStatus", {}).get("S") != "PENDING"
            ):
                return

            plain_run = plain_attributes(run)
            snapshots = query_snapshots(self.client, archive_id)
            frontier = query_frontier(self.client, archive_id)
            document = manifest_document(plain_run, snapshots, frontier)
            body = json.dumps(document, sort_keys=True, separators=(",", ":")).encode()

            digest = hashlib.sha256(body).hexdigest()
            key = manifest_key(archive_id)

            self.s3_client.put_object(
                Bucket=ARCHIVE_MANIFESTS_BUCKET,
                Key=key,
                Body=body,
                ContentType="application/json",
            )

            metadata = self.s3_client.head_object(
                Bucket=ARCHIVE_MANIFESTS_BUCKET,
                Key=key,
            )

            artifact = artifact_document(
                ArtifactReference(
                    bucket=ARCHIVE_MANIFESTS_BUCKET,
                    key=key,
                    sha256=digest,
                    size_bytes=len(body),
                    version_id=metadata.get("VersionId"),
                )
            )

            now = self.clock()
            occurred_at = plain_run["closedAt"]
            message_id = manifest_message_id(archive_id)
            seed_ok = seed_succeeded(plain_run, frontier)

            transaction = finalize_transaction(
                archive_id=archive_id,
                artifact=artifact,
                digest=digest,
                occurred_at=occurred_at,
                message_id=message_id,
                now=now,
                seed_ok=seed_ok,
                captured_count=len(snapshots),
                failed_count=sum(1 for item in frontier if item.get("state") == "FAILED"),
            )

            try:
                self.client.transact_write_items(TransactItems=transaction)
            except ClientError as error:
                if not is_transaction_canceled(error):
                    raise

                current = read_run(self.client, archive_id)

                if current is not None and is_published_manifest(current, digest):
                    existing = read_outbox(self.client, message_id)

                    if existing is not None and is_crawl_completed_message(
                        existing, archive_id, digest
                    ):
                        return

                raise ConditionalWriteRejected from error

        await asyncio.to_thread(finalize)
