from datetime import UTC, datetime

import pytest
from mypy_boto3_dynamodb.client import DynamoDBClient
from support.clock import Clock
from support.domain import (
    frontier_item,
    outbox_items,
    run_item,
    seed_frontier,
    seed_run,
    set_run_auth_generation,
    snapshot_item,
)

from adapters.persistence.dynamodb.task import DynamoDBTaskRepository
from domain.capture import (
    ArtifactReference,
    AuthGenerationChanged,
    CaptureOutcome,
    PageCapture,
    TaskClaim,
)


@pytest.mark.integration
async def test_task_completion_commits_snapshot_and_page_captured_once(
    dynamodb: DynamoDBClient,
    clock: Clock,
) -> None:
    seed_run(dynamodb)
    seed_frontier(dynamodb)

    repository = DynamoDBTaskRepository(
        client=dynamodb,
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

    assert snapshot["warcArtifacts"]["L"][0]["M"] == {
        "bucket": {"S": "capture-artifacts"},
        "key": {"S": "capture-staging/archive-1/url-1/attempt-1/snapshot-1/capture.warc.gz"},
        "sha256": {"S": "a" * 64},
        "sizeBytes": {"N": "128"},
    }

    assert run["outstandingPages"] == {"N": "0"}
    assert run["completedPages"] == {"N": "1"}
    assert run["failedPages"] == {"N": "0"}
    assert run["admission"] == {"S": "CLOSED"}
    assert run["manifestStatus"] == {"S": "PENDING"}
    assert run["closedAt"] == {
        "S": datetime.fromtimestamp(clock(), UTC).isoformat().replace("+00:00", "Z")
    }

    events = outbox_items(dynamodb)

    assert len(events) == 1
    assert events[0]["type"] == {"S": "PageCaptured"}
    assert events[0]["payload"]["M"]["snapshotId"] == {"S": "snapshot-1"}


@pytest.mark.integration
async def test_task_completion_keeps_admission_open_while_pages_remain(
    dynamodb: DynamoDBClient,
    clock: Clock,
) -> None:
    seed_run(dynamodb, admitted_pages=2)
    seed_frontier(dynamodb)

    repository = DynamoDBTaskRepository(
        client=dynamodb,
        lease_duration=30,
        clock=clock,
    )

    claim = await repository.claim("archive-1", "url-1")

    assert claim is not None

    await repository.complete(
        CaptureOutcome(
            archive_id="archive-1",
            url_key="url-1",
            attempt_id=claim.attempt_id,
            fence=claim.fence,
            snapshot_id="snapshot-remaining",
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
                    key="capture-staging/archive-1/url-1/snapshot-remaining/capture.warc.gz",
                    sha256="d" * 64,
                    size_bytes=128,
                ),
            ),
        )
    )

    run = run_item(dynamodb)

    assert run["outstandingPages"] == {"N": "1"}
    assert run["admission"] == {"S": "OPEN"}
    assert "closedAt" not in run
    assert "manifestStatus" not in run


@pytest.mark.integration
async def test_task_completion_accepts_the_current_auth_generation(
    dynamodb: DynamoDBClient,
    clock: Clock,
) -> None:
    seed_run(dynamodb, auth_generation=1)
    seed_frontier(dynamodb)

    repository = DynamoDBTaskRepository(
        client=dynamodb,
        lease_duration=30,
        clock=clock,
    )

    claim = await repository.claim("archive-1", "url-1")

    assert claim is not None

    await repository.complete(
        CaptureOutcome(
            archive_id="archive-1",
            url_key="url-1",
            attempt_id=claim.attempt_id,
            fence=claim.fence,
            snapshot_id="snapshot-auth",
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
                    key="capture-staging/archive-1/url-1/attempt-1/snapshot-auth/capture.warc.gz",
                    sha256="b" * 64,
                    size_bytes=128,
                ),
            ),
            auth_generation=1,
        )
    )

    assert frontier_item(dynamodb)["state"] == {"S": "COMPLETED"}


@pytest.mark.integration
async def test_task_completion_rejects_a_stale_auth_generation(
    dynamodb: DynamoDBClient,
    clock: Clock,
) -> None:
    seed_run(dynamodb, auth_generation=1)
    seed_frontier(dynamodb)

    repository = DynamoDBTaskRepository(
        client=dynamodb,
        lease_duration=30,
        clock=clock,
    )

    claim = await repository.claim("archive-1", "url-1")

    assert claim is not None

    set_run_auth_generation(dynamodb, 2)

    with pytest.raises(AuthGenerationChanged):
        await repository.complete(
            CaptureOutcome(
                archive_id="archive-1",
                url_key="url-1",
                attempt_id=claim.attempt_id,
                fence=claim.fence,
                snapshot_id="snapshot-stale",
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
                        key=(
                            "capture-staging/archive-1/url-1/attempt-1/"
                            "snapshot-stale/capture.warc.gz"
                        ),
                        sha256="c" * 64,
                        size_bytes=128,
                    ),
                ),
                auth_generation=1,
            )
        )

    assert frontier_item(dynamodb)["state"] == {"S": "CLAIMED"}
    assert outbox_items(dynamodb) == []


@pytest.mark.integration
async def test_task_failure_decrements_outstanding_pages(
    dynamodb: DynamoDBClient,
    clock: Clock,
) -> None:
    seed_run(dynamodb)
    seed_frontier(dynamodb)

    repository = DynamoDBTaskRepository(
        client=dynamodb,
        lease_duration=30,
        clock=clock,
    )

    claim = await repository.claim("archive-1", "url-1")

    assert claim is not None

    await repository.fail(claim, "navigation_failed", "browser capture failed")

    run = run_item(dynamodb)

    assert run["outstandingPages"] == {"N": "0"}
    assert run["failedPages"] == {"N": "1"}
    assert run["admission"] == {"S": "CLOSED"}
    assert run["manifestStatus"] == {"S": "PENDING"}
    assert run["closedAt"] == {
        "S": datetime.fromtimestamp(clock(), UTC).isoformat().replace("+00:00", "Z")
    }


@pytest.mark.integration
async def test_task_failure_keeps_admission_open_while_pages_remain(
    dynamodb: DynamoDBClient,
    clock: Clock,
) -> None:
    seed_run(dynamodb, admitted_pages=2)
    seed_frontier(dynamodb)

    repository = DynamoDBTaskRepository(
        client=dynamodb,
        lease_duration=30,
        clock=clock,
    )

    claim = await repository.claim("archive-1", "url-1")

    assert claim is not None

    await repository.fail(claim, "navigation_failed", "browser capture failed")

    run = run_item(dynamodb)

    assert run["outstandingPages"] == {"N": "1"}
    assert run["failedPages"] == {"N": "1"}
    assert run["admission"] == {"S": "OPEN"}
    assert "closedAt" not in run


@pytest.mark.integration
async def test_task_completion_notifies_finalizer_when_run_closes(
    dynamodb: DynamoDBClient,
    clock: Clock,
) -> None:
    closed: list[str] = []

    async def on_closed(archive_id: str) -> None:
        closed.append(archive_id)

    seed_run(dynamodb)
    seed_frontier(dynamodb)

    repository = DynamoDBTaskRepository(
        client=dynamodb,
        lease_duration=30,
        clock=clock,
        on_closed=on_closed,
    )

    claim = await repository.claim("archive-1", "url-1")

    assert claim is not None

    await repository.complete(outcome_for(claim))

    assert closed == ["archive-1"]


@pytest.mark.integration
async def test_task_failure_notifies_finalizer_when_run_closes(
    dynamodb: DynamoDBClient,
    clock: Clock,
) -> None:
    closed: list[str] = []

    async def on_closed(archive_id: str) -> None:
        closed.append(archive_id)

    seed_run(dynamodb)
    seed_frontier(dynamodb)

    repository = DynamoDBTaskRepository(
        client=dynamodb,
        lease_duration=30,
        clock=clock,
        on_closed=on_closed,
    )

    claim = await repository.claim("archive-1", "url-1")

    assert claim is not None

    await repository.fail(claim, "navigation_failed", "browser capture failed")

    assert closed == ["archive-1"]


def outcome_for(claim: TaskClaim) -> CaptureOutcome:
    return CaptureOutcome(
        archive_id="archive-1",
        url_key="url-1",
        attempt_id=claim.attempt_id,
        fence=claim.fence,
        snapshot_id="snapshot-finalizer-notification",
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
                key="capture-staging/archive-1/url-1/capture.warc.gz",
                sha256="a" * 64,
                size_bytes=128,
            ),
        ),
    )
