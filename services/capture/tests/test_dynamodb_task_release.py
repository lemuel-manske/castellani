import pytest
from support.dynamodb import FakeClock, FakeDynamoDBFrontierClient

from adapters.persistence.dynamodb.task_claims import (
    DynamoDBTaskClaims,
    TaskClaimLostError,
)


async def test_release_returns_the_task_to_pending_and_records_capture_page() -> None:
    clock = FakeClock()
    client = FakeDynamoDBFrontierClient()

    client.runs["archive-1"] = {
        "archiveId": {"S": "archive-1"},
        "admission": {"S": "OPEN"},
    }
    client.frontier[("archive-1", "url-1")] = {
        "archiveId": {"S": "archive-1"},
        "urlKey": {"S": "url-1"},
        "url": {"S": "https://example.org/"},
        "depth": {"N": "2"},
        "state": {"S": "PENDING"},
    }

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

    task = client.frontier[("archive-1", "url-1")]
    assert task["state"] == {"S": "PENDING"}
    assert "attemptId" not in task
    assert "leaseUntil" not in task
    assert task["fence"] == {"N": "1"}

    assert len(client.outbox) == 1
    message = next(iter(client.outbox.values()))

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


async def test_releasing_the_same_claim_twice_is_idempotent() -> None:
    client = FakeDynamoDBFrontierClient()
    client.runs["archive-1"] = {
        "archiveId": {"S": "archive-1"},
        "admission": {"S": "OPEN"},
    }
    client.frontier[("archive-1", "url-1")] = {
        "archiveId": {"S": "archive-1"},
        "urlKey": {"S": "url-1"},
        "url": {"S": "https://example.org/"},
        "depth": {"N": "0"},
        "state": {"S": "PENDING"},
    }

    claims = DynamoDBTaskClaims(
        client=client,
        frontier_table_name="capture_frontier",
        runs_table_name="capture_runs",
        lease_duration=30,
        attempt_id_factory=lambda: "attempt-1",
    )

    claim = await claims.claim("archive-1", "url-1")
    assert claim is not None

    await claims.release(claim)
    await claims.release(claim)

    assert len(client.outbox) == 1
    assert client.frontier[("archive-1", "url-1")]["state"] == {"S": "PENDING"}


async def test_stale_claim_cannot_release_a_reclaimed_task() -> None:
    clock = FakeClock()
    client = FakeDynamoDBFrontierClient()
    client.runs["archive-1"] = {
        "archiveId": {"S": "archive-1"},
        "admission": {"S": "OPEN"},
    }
    client.frontier[("archive-1", "url-1")] = {
        "archiveId": {"S": "archive-1"},
        "urlKey": {"S": "url-1"},
        "url": {"S": "https://example.org/"},
        "depth": {"N": "0"},
        "state": {"S": "PENDING"},
    }

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

    task = client.frontier[("archive-1", "url-1")]
    assert task["attemptId"] == {"S": current.attempt_id}
    assert task["fence"] == {"N": str(current.fence)}
    assert client.outbox == {}


async def test_release_does_not_requeue_a_task_after_run_admission_closes() -> None:
    client = FakeDynamoDBFrontierClient()
    client.runs["archive-1"] = {
        "archiveId": {"S": "archive-1"},
        "admission": {"S": "OPEN"},
    }
    client.frontier[("archive-1", "url-1")] = {
        "archiveId": {"S": "archive-1"},
        "urlKey": {"S": "url-1"},
        "url": {"S": "https://example.org/"},
        "depth": {"N": "0"},
        "state": {"S": "PENDING"},
    }

    claims = DynamoDBTaskClaims(
        client=client,
        frontier_table_name="capture_frontier",
        runs_table_name="capture_runs",
        lease_duration=30,
        attempt_id_factory=lambda: "attempt-1",
    )

    claim = await claims.claim("archive-1", "url-1")
    assert claim is not None

    client.runs["archive-1"]["admission"] = {"S": "CLOSED"}

    with pytest.raises(TaskClaimLostError):
        await claims.release(claim)

    assert client.frontier[("archive-1", "url-1")]["state"] == {"S": "CLAIMED"}
    assert client.outbox == {}
