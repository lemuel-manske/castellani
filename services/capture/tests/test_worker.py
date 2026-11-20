from pathlib import Path

from application.worker import Worker
from domain.task import PageTask, TaskClaim
from support.worker import (
    FakeArtifactStore,
    FakeCapacity,
    FakeRepository,
    FailingPageExecutor,
)


async def test_worker_discards_attempt_artifacts_after_capture_failure(tmp_path: Path) -> None:
    claim = TaskClaim(
        task=PageTask(
            archive_id="archive-1",
            url_key="url-1",
            url="https://example.org/",
            depth=0,
        ),
        attempt_id="attempt-1",
        fence=1,
        lease_until=100.0,
    )
    repository = FakeRepository(claim)
    artifacts = FakeArtifactStore(tmp_path)
    worker = Worker(
        repository=repository,
        capacity=FakeCapacity(),
        executor=FailingPageExecutor(),
        artifacts=artifacts,
    )

    claimed = await worker.execute("archive-1", "url-1")

    assert claimed
    assert repository.failed == (claim, "capture_failed", "browser capture failed")
    assert artifacts.discarded == [(claim, tmp_path)]
    assert repository.completed is None
