import pytest
from support.dynamodb import FakeClock
from support.local_dynamodb import (
    frontier_item,
    outbox_items,
    seed_frontier,
    seed_run,
    set_run_admission,
)

from adapters.persistence.dynamodb.task_claims import (
    DynamoDBTaskClaims,
    TaskClaimLostError,
)


async def test_release_returns_the_task_to_pending_and_records_capture_page(dynamodb_client) -> None:
    clock = FakeClock()
    client = dynamodb_client

    seed_run(client)
    seed_frontier(client, depth=2)

    claims = DynamoDBTaskClaims(
        client=client,
        frontier_table_name="capture_frontier",
        runs_table_name="capture_runs",
        lease_duration=30,
        clock=clock,
        attempt_id_factory=lambda: "attempt-1",
    )

    claim = await claims.claim("archive-1", "url-1")
    assert claim is not None

    await claims.release(claim)

    task = frontier_item(client)
    assert task["state"] == {"S": "PENDING"}
    assert "attemptId" not in task
    assert "leaseUntil" not in task
    assert task["fence"] == {"N": "1"}

    assert len(outbox_items(client)) == 1
    message = outbox_items(client)[0]

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
    assert message["nextAttemptAt"] == {"N": str(clock())}


async def test_releasing_the_same_claim_twice_is_idempotent(dynamodb_client) -> None:
    clock = FakeClock()
    client = dynamodb_client
    seed_run(client)
    seed_frontier(client, depth=0)

    claims = DynamoDBTaskClaims(
        client=client,
        frontier_table_name="capture_frontier",
        runs_table_name="capture_runs",
        lease_duration=30,
        clock=clock,
        attempt_id_factory=lambda: "attempt-1",
    )

    claim = await claims.claim("archive-1", "url-1")
    assert claim is not None

    await claims.release(claim)
    clock.advance(1)
    await claims.release(claim)

    assert len(outbox_items(client)) == 1
    assert frontier_item(client)["state"] == {"S": "PENDING"}


async def test_stale_claim_cannot_release_a_reclaimed_task(dynamodb_client) -> None:
    clock = FakeClock()
    client = dynamodb_client
    seed_run(client)
    seed_frontier(client, depth=0)

    attempt_ids = iter(("attempt-1", "attempt-2"))
    claims = DynamoDBTaskClaims(
        client=client,
        frontier_table_name="capture_frontier",
        runs_table_name="capture_runs",
        lease_duration=30,
        clock=clock,
        attempt_id_factory=lambda: next(attempt_ids),
    )

    stale = await claims.claim("archive-1", "url-1")
    assert stale is not None

    clock.advance(31)

    current = await claims.claim("archive-1", "url-1")
    assert current is not None

    with pytest.raises(TaskClaimLostError):
        await claims.release(stale)

    task = frontier_item(client)
    assert task["attemptId"] == {"S": current.attempt_id}
    assert task["fence"] == {"N": str(current.fence)}
    assert outbox_items(client) == {}


async def test_release_does_not_requeue_a_task_after_run_admission_closes(dynamodb_client) -> None:
    client = dynamodb_client
    seed_run(client)
    seed_frontier(client, depth=0)

    claims = DynamoDBTaskClaims(
        client=client,
        frontier_table_name="capture_frontier",
        runs_table_name="capture_runs",
        lease_duration=30,
        attempt_id_factory=lambda: "attempt-1",
    )

    claim = await claims.claim("archive-1", "url-1")
    assert claim is not None

    set_run_admission(client, "CLOSED")

    with pytest.raises(TaskClaimLostError):
        await claims.release(claim)

    assert frontier_item(client)["state"] == {"S": "CLAIMED"}
    assert outbox_items(client) == {}
