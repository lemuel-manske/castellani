import pytest
from mypy_boto3_dynamodb.client import DynamoDBClient
from support.clock import FakeClock
from support.domain import frontier_item, outbox_items, run_item, seed_frontier, seed_run

from adapters.persistence.dynamodb.task import (
    DynamoDBTaskRepository,
    TaskClaimLostError,
)


def new_repository(
    dynamodb: DynamoDBClient,
    clock: FakeClock,
    max_attempts: int = 3,
) -> DynamoDBTaskRepository:
    return DynamoDBTaskRepository(
        client=dynamodb,
        frontier_table_name="capture_frontier",
        runs_table_name="capture_runs",
        lease_duration=30,
        clock=clock,
        max_attempts=max_attempts,
        retry_base_delay=30,
    )


@pytest.mark.integration
async def test_failed_capture_retries_with_bounded_exponential_backoff_then_becomes_terminal(
    dynamodb: DynamoDBClient,
    clock: FakeClock,
) -> None:
    seed_run(dynamodb)
    seed_frontier(dynamodb)

    repository = new_repository(dynamodb, clock)

    first = await repository.claim("archive-1", "url-1")
    assert first is not None

    await repository.fail(first, "browser_unavailable", "browser crashed")

    task = frontier_item(dynamodb)
    assert task["state"] == {"S": "PENDING"}
    assert task["failureCount"] == {"N": "1"}
    assert task["nextAttemptAt"] == {"N": str(clock() + 30)}
    assert run_item(dynamodb)["outstandingPages"] == {"N": "1"}
    assert len(outbox_items(dynamodb)) == 1

    # An early or duplicate delivery must not bypass the persisted retry time.
    assert await repository.claim("archive-1", "url-1") is None

    clock.advance(30)
    second = await repository.claim("archive-1", "url-1")
    assert second is not None
    assert second.fence == first.fence + 1

    await repository.fail(second, "browser_unavailable", "browser crashed again")

    task = frontier_item(dynamodb)
    assert task["state"] == {"S": "PENDING"}
    assert task["failureCount"] == {"N": "2"}
    assert task["nextAttemptAt"] == {"N": str(clock() + 60)}
    assert len(outbox_items(dynamodb)) == 2

    clock.advance(60)
    third = await repository.claim("archive-1", "url-1")
    assert third is not None
    assert third.fence == second.fence + 1

    await repository.fail(third, "browser_unavailable", "retry budget exhausted")

    task = frontier_item(dynamodb)
    assert task["state"] == {"S": "FAILED"}
    assert task["failureCount"] == {"N": "3"}
    assert "nextAttemptAt" not in task
    assert task["failureReason"] == {"S": "browser_unavailable"}

    run = run_item(dynamodb)
    assert run["outstandingPages"] == {"N": "0"}
    assert run["failedPages"] == {"N": "1"}
    assert len(outbox_items(dynamodb)) == 2


@pytest.mark.integration
async def test_repeating_the_same_failure_is_idempotent(
    dynamodb: DynamoDBClient,
    clock: FakeClock,
) -> None:
    seed_run(dynamodb)
    seed_frontier(dynamodb)

    repository = new_repository(dynamodb, clock)

    claim = await repository.claim("archive-1", "url-1")
    assert claim is not None

    await repository.fail(claim, "browser_unavailable", "browser crashed")
    clock.advance(1)
    await repository.fail(claim, "browser_unavailable", "browser crashed")

    task = frontier_item(dynamodb)
    assert task["state"] == {"S": "PENDING"}
    assert task["failureCount"] == {"N": "1"}
    assert len(outbox_items(dynamodb)) == 1
    assert run_item(dynamodb)["outstandingPages"] == {"N": "1"}


@pytest.mark.integration
async def test_stale_attempt_cannot_fail_a_reclaimed_task(
    dynamodb: DynamoDBClient,
    clock: FakeClock,
) -> None:
    seed_run(dynamodb)
    seed_frontier(dynamodb)

    repository = new_repository(dynamodb, clock)

    stale = await repository.claim("archive-1", "url-1")
    assert stale is not None

    clock.advance(31)
    current = await repository.claim("archive-1", "url-1")
    assert current is not None

    with pytest.raises(TaskClaimLostError):
        await repository.fail(stale, "browser_unavailable", "late failure")

    task = frontier_item(dynamodb)
    assert task["state"] == {"S": "CLAIMED"}
    assert task["attemptId"] == {"S": current.attempt_id}
    assert task["fence"] == {"N": str(current.fence)}
    assert task.get("failureCount", {"N": "0"}) == {"N": "0"}
    assert outbox_items(dynamodb) == []


@pytest.mark.integration
async def test_first_failure_is_terminal_when_retry_budget_is_one(
    dynamodb: DynamoDBClient,
    clock: FakeClock,
) -> None:
    seed_run(dynamodb)
    seed_frontier(dynamodb)

    repository = new_repository(dynamodb, clock, max_attempts=1)

    claim = await repository.claim("archive-1", "url-1")
    assert claim is not None

    await repository.fail(claim, "invalid_capture", "capture cannot be retried")

    task = frontier_item(dynamodb)
    assert task["state"] == {"S": "FAILED"}
    assert task["failureCount"] == {"N": "1"}
    assert run_item(dynamodb)["outstandingPages"] == {"N": "0"}
    assert run_item(dynamodb)["failedPages"] == {"N": "1"}
    assert outbox_items(dynamodb) == []
