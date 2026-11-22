import pytest
from mypy_boto3_dynamodb.client import DynamoDBClient
from support.clock import FakeClock
from support.domain import (
    frontier_item,
    outbox_items,
    seed_frontier,
    seed_run,
    set_run_admission,
)

from adapters.persistence.dynamodb.task import (
    DynamoDBTaskRepository,
    TaskClaimLostError,
)


@pytest.mark.integration
async def test_release_requeues_and_records_capture_page(
    dynamodb: DynamoDBClient,
    clock: FakeClock,
) -> None:
    seed_run(dynamodb)
    seed_frontier(dynamodb, depth=2)

    claims = DynamoDBTaskRepository(
        client=dynamodb,
        frontier_table_name="capture_frontier",
        runs_table_name="capture_runs",
        lease_duration=30,
        clock=clock,
    )

    claim = await claims.claim("archive-1", "url-1")
    assert claim is not None

    await claims.release(claim)

    task = frontier_item(dynamodb)

    assert "attemptId" not in task
    assert "leaseUntil" not in task

    assert task["state"] == {"S": "PENDING"}
    assert task["fence"] == {"N": "1"}
    assert task["attemptCount"] == {"N": "0"}

    assert len(outbox_items(dynamodb)) == 1

    message = outbox_items(dynamodb)[0]

    assert message["correlationId"] == {"S": "archive-1"}
    assert message["type"] == {"S": "CapturePage"}
    assert message["version"] == {"N": "1"}
    assert message["payload"] == {
        "M": {
            "archiveId": {"S": "archive-1"},
            "urlKey": {"S": "url-1"},
        }
    }
    assert message["status"] == {"S": "PENDING"}
    assert message["attempts"] == {"N": "0"}


@pytest.mark.integration
async def test_releasing_the_same_claim_twice_is_idempotent(
    dynamodb: DynamoDBClient,
    clock: FakeClock,
) -> None:
    seed_run(dynamodb)
    seed_frontier(dynamodb, depth=0)

    claims = DynamoDBTaskRepository(
        client=dynamodb,
        frontier_table_name="capture_frontier",
        runs_table_name="capture_runs",
        lease_duration=30,
        clock=clock,
    )

    claim = await claims.claim("archive-1", "url-1")
    assert claim is not None

    await claims.release(claim)

    clock.advance(1)

    await claims.release(claim)

    assert len(outbox_items(dynamodb)) == 1
    assert frontier_item(dynamodb)["state"] == {"S": "PENDING"}


@pytest.mark.integration
async def test_stale_claim_cannot_release_reclaimed_task(
    dynamodb: DynamoDBClient,
    clock: FakeClock,
) -> None:
    seed_run(dynamodb)
    seed_frontier(dynamodb, depth=0)

    claims = DynamoDBTaskRepository(
        client=dynamodb,
        frontier_table_name="capture_frontier",
        runs_table_name="capture_runs",
        lease_duration=30,
        clock=clock,
    )

    stale = await claims.claim("archive-1", "url-1")
    assert stale is not None

    clock.advance(31)

    current = await claims.claim("archive-1", "url-1")
    assert current is not None

    with pytest.raises(TaskClaimLostError):
        await claims.release(stale)

    task = frontier_item(dynamodb)

    assert task["attemptId"] == {"S": current.attempt_id}
    assert task["fence"] == {"N": str(current.fence)}
    assert outbox_items(dynamodb) == []


@pytest.mark.integration
async def test_release_does_not_requeue_a_task_after_run_admission_closes(
    dynamodb: DynamoDBClient,
) -> None:
    seed_run(dynamodb)
    seed_frontier(dynamodb, depth=0)

    claims = DynamoDBTaskRepository(
        client=dynamodb,
        frontier_table_name="capture_frontier",
        runs_table_name="capture_runs",
        lease_duration=30,
    )

    claim = await claims.claim("archive-1", "url-1")
    assert claim is not None

    set_run_admission(dynamodb, "CLOSED")

    with pytest.raises(TaskClaimLostError):
        await claims.release(claim)

    assert frontier_item(dynamodb)["state"] == {"S": "CLAIMED"}
    assert outbox_items(dynamodb) == []
