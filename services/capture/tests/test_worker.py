import time
from pathlib import Path

from application.worker import LeaseLostError, Worker
from domain.task import PageTask, TaskClaim
from support.worker import (
    BlockingPageExecutor,
    ExpiringRepository,
    FakeArtifactStore,
    FakeCapacity,
    FakeRepository,
    FailingPageExecutor,
    ShortLeaseCapacity,
    ShortLeaseRepository,
    SlowPageExecutor,
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
        lease_until=time.time() + 60,
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


async def test_worker_renews_task_and_capacity_leases_during_capture(tmp_path: Path) -> None:
    claim = TaskClaim(
        task=PageTask(
            archive_id="archive-1",
            url_key="url-1",
            url="https://example.org/",
            depth=0,
        ),
        attempt_id="attempt-1",
        fence=1,
        lease_until=time.time() + 0.06,
    )
    repository = ShortLeaseRepository(claim)
    capacity = ShortLeaseCapacity()
    worker = Worker(
        repository=repository,
        capacity=capacity,
        executor=SlowPageExecutor(),
        artifacts=FakeArtifactStore(tmp_path),
    )

    claimed = await worker.execute("archive-1", "url-1")

    assert claimed
    assert repository.renewals >= 1
    assert capacity.renewals >= 1
    assert repository.completed is not None


async def test_worker_stops_capture_when_task_lease_renewal_fails(tmp_path: Path) -> None:
    claim = TaskClaim(
        task=PageTask(
            archive_id="archive-1",
            url_key="url-1",
            url="https://example.org/",
            depth=0,
        ),
        attempt_id="attempt-1",
        fence=1,
        lease_until=time.time() + 0.06,
    )
    repository = ExpiringRepository(claim)
    artifacts = FakeArtifactStore(tmp_path)
    executor = BlockingPageExecutor()
    worker = Worker(
        repository=repository,
        capacity=FakeCapacity(),
        executor=executor,
        artifacts=artifacts,
    )

    try:
        await worker.execute("archive-1", "url-1")
    except LeaseLostError:
        pass
    else:
        raise AssertionError("Expected lease loss to abort the capture")

    assert executor.started.is_set()
    assert executor.cancelled.is_set()
    assert repository.failed is None
    assert repository.completed is None
    assert artifacts.discarded == [(claim, tmp_path)]


async def test_worker_stops_capture_when_capacity_lease_renewal_fails(tmp_path: Path) -> None:
    claim = TaskClaim(
        task=PageTask(
            archive_id="archive-1",
            url_key="url-1",
            url="https://example.org/",
            depth=0,
        ),
        attempt_id="attempt-1",
        fence=1,
        lease_until=time.time() + 0.06,
    )
    repository = FakeRepository(claim)
    artifacts = FakeArtifactStore(tmp_path)
    executor = BlockingPageExecutor()
    worker = Worker(
        repository=repository,
        capacity=ExpiringCapacity(),
        executor=executor,
        artifacts=artifacts,
    )

    try:
        await worker.execute("archive-1", "url-1")
    except LeaseLostError:
        pass
    else:
        raise AssertionError("Expected capacity lease loss to abort the capture")

    assert executor.started.is_set()
    assert executor.cancelled.is_set()
    assert repository.failed is None
    assert repository.completed is None
    assert artifacts.discarded == [(claim, tmp_path)]
