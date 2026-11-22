from datetime import UTC, datetime
from pathlib import Path

import pytest
from mypy_boto3_dynamodb.client import DynamoDBClient
from support.domain import frontier_item, outbox_items, seed_frontier, seed_run

from adapters.artifacts.local import LocalArtifactStore
from adapters.persistence.dynamodb.alloc import DynamoDBCaptureAllocator
from adapters.persistence.dynamodb.task import DynamoDBTaskRepository
from domain import PageCapture
from utils.fn import noop
from worker import CaptureArtifact
from worker.worker import ConcreteCaptureWorker


@pytest.mark.integration
async def test_worker_discards_real_attempt_artifacts_after_capture_failure(
    dynamodb: DynamoDBClient,
    tmp_path: Path,
) -> None:
    seed_run(dynamodb)
    seed_frontier(dynamodb)

    artifacts = LocalArtifactStore(tmp_path)

    worker = new_worker(dynamodb, artifacts, FailingExecutor())

    assert await worker("archive-1", "url-1")

    task = frontier_item(dynamodb)

    assert task["state"] == {"S": "FAILED"}
    assert task["failureReason"] == {"S": "capture_failed"}
    assert task["failureMessage"] == {"S": "browser capture failed"}
    assert not (tmp_path / "attempt-1").exists()


@pytest.mark.integration
async def test_worker_completes_with_real_dynamodb_and_artifact_storage(
    dynamodb: DynamoDBClient,
    tmp_path: Path,
) -> None:
    seed_run(dynamodb)
    seed_frontier(dynamodb)

    artifacts = LocalArtifactStore(tmp_path)

    worker = new_worker(dynamodb, artifacts, SuccessfulExecutor())

    assert await worker("archive-1", "url-1")

    assert frontier_item(dynamodb)["state"] == {"S": "COMPLETED"}
    assert (tmp_path / "attempt-1" / "capture.warc.gz").read_bytes() == b"capture"


@pytest.mark.integration
async def test_worker_requeues_task_when_real_allocator_has_no_available_slot(
    dynamodb: DynamoDBClient,
    tmp_path: Path,
) -> None:
    seed_run(dynamodb)
    seed_frontier(dynamodb)

    allocator = DynamoDBCaptureAllocator(
        client=dynamodb,
        table_name="capture_browser_slots",
        slot_count=1,
        lease_duration=30,
    )

    held = await allocator.reserve("other-attempt")
    assert held is not None

    worker = new_worker(dynamodb, LocalArtifactStore(tmp_path), UnexpectedExecutor())

    assert await worker("archive-1", "url-1")
    assert frontier_item(dynamodb)["state"] == {"S": "PENDING"}
    assert len(outbox_items(dynamodb)) == 1


class FailingExecutor:
    async def execute(self, url: str, output_dir: Path) -> CaptureArtifact:
        noop(url, output_dir)

        raise RuntimeError("browser capture failed")


class SuccessfulExecutor:
    async def execute(self, url: str, output_dir: Path) -> CaptureArtifact:
        (output_dir / "capture.warc.gz").write_bytes(b"capture")

        return CaptureArtifact(
            capture=PageCapture(
                requested_url=url,
                final_url=url,
                redirect_chain=(),
                status_code=200,
                content_type="text/html",
                title="Example",
                captured_at=datetime(2026, 11, 21, 12, 0, tzinfo=UTC),
                discovered_urls=(),
            ),
            blocked_urls=(),
            warc_files=(output_dir / "capture.warc.gz",),
        )


class UnexpectedExecutor:
    async def execute(self, url: str, output_dir: Path) -> CaptureArtifact:
        noop(url, output_dir)

        raise AssertionError("the executor must not run when capacity is unavailable")


def new_worker(
    dynamodb: DynamoDBClient,
    artifacts: LocalArtifactStore,
    executor: FailingExecutor | SuccessfulExecutor | UnexpectedExecutor,
) -> ConcreteCaptureWorker:
    return ConcreteCaptureWorker(
        task_repository=DynamoDBTaskRepository(
            client=dynamodb,
            frontier_table_name="capture_frontier",
            runs_table_name="capture_runs",
            lease_duration=30,
        ),
        capture_allocator=DynamoDBCaptureAllocator(
            client=dynamodb,
            table_name="capture_browser_slots",
            slot_count=1,
            lease_duration=30,
        ),
        executor=executor,
        artifacts=artifacts,
    )
