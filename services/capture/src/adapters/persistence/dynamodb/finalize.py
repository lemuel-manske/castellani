import asyncio
import hashlib
import json
import time
from collections.abc import Callable
from typing import Any

from botocore.exceptions import ClientError

from domain.capture import CrawlFinalizer, manifest_key, manifest_message_id
from topology.buckets import ARCHIVE_MANIFESTS_BUCKET
from topology.tables import OUTBOX_TABLE, RUNS_TABLE

from .error_handling import is_transaction_canceled
from .queries.finalize import (
    artifact_fields,
    is_crawl_completed_message,
    manifest_document,
    query_frontier,
    query_snapshots,
    seed_succeeded,
)
from .queries.task import read_outbox, read_run
from .task import ConditionalWriteRejected


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
        await asyncio.to_thread(self._finalize, archive_id)

    def _finalize(self, archive_id: str) -> None:
        run = read_run(self.client, archive_id)

        if run is None:
            raise RuntimeError("Capture run disappeared during finalization")

        if (
            run.get("admission", {}).get("S") != "CLOSED"
            or run.get("manifestStatus", {}).get("S") != "PENDING"
        ):
            return

        snapshots = query_snapshots(self.client, archive_id)
        frontier = query_frontier(self.client, archive_id)
        document = manifest_document(run, snapshots, frontier)
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

        artifact = artifact_fields(
            {
                "bucket": ARCHIVE_MANIFESTS_BUCKET,
                "key": key,
                "sha256": digest,
                "sizeBytes": len(body),
                "versionId": metadata.get("VersionId"),
            }
        )

        now = self.clock()
        occurred_at = run["closedAt"]["S"]
        message_id = manifest_message_id(archive_id)
        payload: dict[str, Any] = {
            "archiveId": archive_id,
            "manifest": artifact,
            "manifestDigest": digest,
            "seedSucceeded": seed_succeeded(run, frontier),
            "capturedCount": len(snapshots),
            "failedCount": sum(1 for item in frontier if item.get("state") == "FAILED"),
        }

        transaction = [
            {
                "Update": {
                    "TableName": RUNS_TABLE,
                    "Key": {"archiveId": {"S": archive_id}},
                    "UpdateExpression": (
                        "SET #status = :published, #key = :key, #digest = :digest"
                    ),
                    "ConditionExpression": "#status = :pending",
                    "ExpressionAttributeNames": {
                        "#status": "manifestStatus",
                        "#key": "manifestKey",
                        "#digest": "manifestDigest",
                    },
                    "ExpressionAttributeValues": {
                        ":pending": {"S": "PENDING"},
                        ":published": {"S": "PUBLISHED"},
                        ":key": {"S": key},
                        ":digest": {"S": digest},
                    },
                }
            },
            {
                "Put": {
                    "TableName": OUTBOX_TABLE,
                    "Item": {
                        "messageId": {"S": message_id},
                        "correlationId": {"S": archive_id},
                        "type": {"S": "CrawlCompleted"},
                        "version": {"N": "1"},
                        "occurredAt": {"S": occurred_at},
                        "payload": {"M": _envelope_attributes(payload)},
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
            self.client.transact_write_items(TransactItems=transaction)
        except ClientError as error:
            if not is_transaction_canceled(error):
                raise

            current = read_run(self.client, archive_id)

            if (
                current is not None
                and current.get("manifestStatus", {}).get("S") == "PUBLISHED"
                and current.get("manifestDigest", {}).get("S") == digest
            ):
                existing = read_outbox(self.client, message_id)

                if existing is not None and is_crawl_completed_message(
                    existing, archive_id, digest
                ):
                    return

            raise ConditionalWriteRejected from error


def _envelope_attributes(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "archiveId": {"S": payload["archiveId"]},
        "manifest": {"M": _artifact_map(payload["manifest"])},
        "manifestDigest": {"S": payload["manifestDigest"]},
        "seedSucceeded": {"BOOL": payload["seedSucceeded"]},
        "capturedCount": {"N": str(payload["capturedCount"])},
        "failedCount": {"N": str(payload["failedCount"])},
    }


def _artifact_map(artifact: dict[str, Any]) -> dict[str, Any]:
    values: dict[str, Any] = {
        "bucket": {"S": artifact["bucket"]},
        "key": {"S": artifact["key"]},
        "sha256": {"S": artifact["sha256"]},
        "sizeBytes": {"N": str(artifact["sizeBytes"])},
    }

    if "versionId" in artifact:
        values["versionId"] = {"S": artifact["versionId"]}

    return values
