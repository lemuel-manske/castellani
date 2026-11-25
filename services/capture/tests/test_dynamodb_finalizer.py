import hashlib
import json
from typing import Any

import pytest
from mypy_boto3_dynamodb.client import DynamoDBClient
from support.clock import FakeClock
from support.domain import (
    outbox_item,
    outbox_items,
    run_item,
    seed_frontier,
    seed_run,
    seed_snapshot,
)
from support.s3 import FakeS3

from adapters.messaging.contracts import validate_message
from adapters.persistence.dynamodb.finalize import DynamoDBManifestFinalizer
from adapters.persistence.dynamodb.queries.outbox import message_from_item
from domain.capture import identify_url, manifest_key, manifest_message_id
from topology.buckets import ARCHIVE_MANIFESTS_BUCKET

ARCHIVE_ID = "archive-finalizer"
SEED_URL = "https://example.org/"
CLOSED_AT = "2026-11-25T12:00:00Z"
SEED_KEY = identify_url(SEED_URL).url_key


@pytest.mark.integration
async def test_finalizer_writes_contract_manifest_and_completion_outbox_once(
    dynamodb: DynamoDBClient,
    s3: FakeS3,
    clock: FakeClock,
) -> None:
    seed_closed_run(dynamodb)
    seed_frontier(dynamodb, archive_id=ARCHIVE_ID, url_key=SEED_KEY, state="COMPLETED")
    seed_frontier(
        dynamodb,
        archive_id=ARCHIVE_ID,
        url_key=identify_url("https://example.org/failed").url_key,
        url="https://example.org/failed",
        state="FAILED",
        failure_reason="navigation_failed",
    )
    seed_snapshot(
        dynamodb,
        archive_id=ARCHIVE_ID,
        snapshot_id="snapshot-finalizer",
        url_key=SEED_KEY,
        warc_artifacts=(warc_artifact(),),
    )

    finalizer = DynamoDBManifestFinalizer(
        client=dynamodb,
        s3_client=s3,
        clock=clock,
    )

    await finalizer(ARCHIVE_ID)
    await finalizer(ARCHIVE_ID)

    key = manifest_key(ARCHIVE_ID)
    body, _ = s3.objects[(ARCHIVE_MANIFESTS_BUCKET, key)]
    manifest = json.loads(body)
    digest = hashlib.sha256(body).hexdigest()

    assert manifest == expected_manifest()
    assert run_item(dynamodb, ARCHIVE_ID)["manifestDigest"] == {"S": digest}
    assert run_item(dynamodb, ARCHIVE_ID)["manifestKey"] == {"S": key}
    assert run_item(dynamodb, ARCHIVE_ID)["manifestStatus"] == {"S": "PUBLISHED"}

    items = outbox_items(dynamodb)

    assert len(items) == 1

    envelope = message_from_item(items[0])

    assert validate_message(json.dumps(envelope).encode(), "CrawlCompleted") == envelope
    assert envelope["payload"] == {
        "archiveId": ARCHIVE_ID,
        "manifest": {
            "bucket": ARCHIVE_MANIFESTS_BUCKET,
            "key": key,
            "sha256": digest,
            "sizeBytes": len(body),
            "versionId": "version-1",
        },
        "manifestDigest": digest,
        "seedSucceeded": True,
        "capturedCount": 1,
        "failedCount": 1,
    }
    assert outbox_item(dynamodb, manifest_message_id(ARCHIVE_ID))["messageId"][
        "S"
    ] == manifest_message_id(ARCHIVE_ID)


@pytest.mark.integration
async def test_finalizer_ignores_a_run_that_is_not_awaiting_a_manifest(
    dynamodb: DynamoDBClient,
    s3: FakeS3,
    clock: FakeClock,
) -> None:
    seed_run(
        dynamodb,
        archive_id=ARCHIVE_ID,
        seed_url=SEED_URL,
        closed_at=CLOSED_AT,
        manifest_status="PUBLISHED",
    )

    finalizer = DynamoDBManifestFinalizer(
        client=dynamodb,
        s3_client=s3,
        clock=clock,
    )

    await finalizer(ARCHIVE_ID)

    assert s3.objects == {}
    assert outbox_items(dynamodb) == []


def seed_closed_run(dynamodb: DynamoDBClient) -> None:
    seed_run(
        dynamodb,
        admission="CLOSED",
        archive_id=ARCHIVE_ID,
        seed_url=SEED_URL,
        closed_at=CLOSED_AT,
        manifest_status="PENDING",
    )


def warc_artifact() -> dict[str, Any]:
    return {
        "bucket": {"S": "capture-artifacts"},
        "key": {"S": "capture-staging/snapshot-finalizer/capture.warc.gz"},
        "sha256": {"S": "b" * 64},
        "sizeBytes": {"N": "128"},
        "versionId": {"S": "artifact-version-1"},
    }


def expected_manifest() -> dict[str, Any]:
    return {
        "schemaVersion": 1,
        "archiveId": ARCHIVE_ID,
        "normalizerVersion": "v1",
        "seedUrl": SEED_URL,
        "createdAt": CLOSED_AT,
        "snapshots": [
            {
                "snapshotId": "snapshot-finalizer",
                "urlKey": SEED_KEY,
                "url": "https://example.org/",
                "finalUrl": "https://example.org/final",
                "redirectChain": ["https://example.org/"],
                "minDepth": 0,
                "contentType": "text/html",
                "capturedAt": "2026-11-24T10:00:00Z",
                "warcArtifacts": [
                    {
                        "bucket": "capture-artifacts",
                        "key": "capture-staging/snapshot-finalizer/capture.warc.gz",
                        "sha256": "b" * 64,
                        "sizeBytes": 128,
                        "versionId": "artifact-version-1",
                    }
                ],
            }
        ],
        "failedPages": [
            {
                "urlKey": identify_url("https://example.org/failed").url_key,
                "reasonCode": "navigation_failed",
            }
        ],
    }
