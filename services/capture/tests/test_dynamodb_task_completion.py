from datetime import UTC, datetime

import pytest
from mypy_boto3_dynamodb.client import DynamoDBClient
from support.clock import FakeClock
from support.domain import (
    frontier_item,
    outbox_items,
    run_item,
    seed_frontier,
    seed_run,
    snapshot_item,
)

from adapters.persistence.dynamodb.task import DynamoDBTaskRepository
from domain import ArtifactReference, CaptureOutcome, PageCapture


@pytest.mark.integration
async def test_task_completion_commits_snapshot_and_page_captured_once(
    dynamodb: DynamoDBClient,
    clock: FakeClock,
) -> None:
    seed_run(dynamodb)
    seed_frontier(dynamodb)

    repository = DynamoDBTaskRepository(
        client=dynamodb,
        frontier_table_name="capture_frontier",
        runs_table_name="capture_runs",
        lease_duration=30,
        clock=clock,
    )

    claim = await repository.claim("archive-1", "url-1")

    assert claim is not None

    outcome = CaptureOutcome(
        archive_id="archive-1",
        url_key="url-1",
        attempt_id=claim.attempt_id,
        fence=claim.fence,
        snapshot_id="snapshot-1",
        capture=PageCapture(
            requested_url="https://example.org/",
            final_url="https://example.org/",
            redirect_chain=(),
            status_code=200,
            content_type="text/html",
            title="Example",
            captured_at=datetime(2026, 11, 22, 12, 0, tzinfo=UTC),
            discovered_urls=(),
        ),
        warc_artifacts=(
            ArtifactReference(
                bucket="capture-artifacts",
                key="capture-staging/archive-1/url-1/attempt-1/snapshot-1/capture.warc.gz",
                sha256="a" * 64,
                size_bytes=128,
                version_id="version-1",
            ),
        ),
    )

    await repository.complete(outcome)
    await repository.complete(outcome)

    frontier = frontier_item(dynamodb)
    snapshot = snapshot_item(dynamodb)
    run = run_item(dynamodb)

    assert frontier["state"] == {"S": "COMPLETED"}
    assert frontier["snapshotId"] == {"S": "snapshot-1"}
    assert snapshot["archiveId"] == {"S": "archive-1"}

    assert snapshot["warcArtifacts"]["L"][0]["M"]["versionId"] == {"S": "version-1"}

    assert run["outstandingPages"] == {"N": "0"}
    assert run["completedPages"] == {"N": "1"}

    events = outbox_items(dynamodb)

    assert len(events) == 1
    assert events[0]["type"] == {"S": "PageCaptured"}
    assert events[0]["payload"]["M"]["snapshotId"] == {"S": "snapshot-1"}
