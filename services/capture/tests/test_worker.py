from pathlib import Path

from support.worker import worker_failure_scenario


async def test_worker_discards_attempt_artifacts_after_capture_failure(tmp_path: Path) -> None:
    scenario = worker_failure_scenario(tmp_path)

    claimed = await scenario.worker.execute("archive-1", "url-1")

    assert claimed
    assert scenario.repository.failed == (
        scenario.claim,
        "capture_failed",
        "browser capture failed",
    )
    assert scenario.artifacts.discarded == [(scenario.claim, tmp_path)]
    assert scenario.repository.completed is None
