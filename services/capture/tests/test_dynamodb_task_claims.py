import asyncio

import pytest
from support.dynamodb import FakeClock, FakeDynamoDBFrontierClient

from adapters.persistence.dynamodb.task_claims import (
    DynamoDBTaskClaims,
    TaskClaimLostError,
)


def new_frontier_client() -> FakeDynamoDBFrontierClient:
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

    return client


async def test_claim_acquires_a_pending_task_with_a_new_fencing_generation() -> None:
    clock = FakeClock()
    client = new_frontier_client()
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
    assert claim.task.url == "https://example.org/"
    assert claim.task.depth == 2
    assert claim.attempt_id == "attempt-1"
    assert claim.fence == 1
    assert claim.lease_until == clock() + 30


async def test_claim_does_not_replace_an_active_attempt() -> None:
    client = new_frontier_client()
    attempt_ids = iter(("attempt-1", "attempt-2"))
    claims = DynamoDBTaskClaims(
        client=client,
        frontier_table_name="capture_frontier",
        runs_table_name="capture_runs",
        lease_duration=30,
        attempt_id_factory=lambda: next(attempt_ids),
    )

    first = await claims.claim("archive-1", "url-1")
    second = await claims.claim("archive-1", "url-1")

    assert first is not None
    assert second is None
    assert client.frontier[("archive-1", "url-1")]["attemptId"] == {"S": "attempt-1"}


async def test_expired_claim_is_reclaimed_with_a_higher_fence() -> None:
    clock = FakeClock()
    client = new_frontier_client()
    attempt_ids = iter(("attempt-1", "attempt-2"))
    claims = DynamoDBTaskClaims(
        client=client,
        frontier_table_name="capture_frontier",
        runs_table_name="capture_runs",
        lease_duration=30,
        clock=clock,
        attempt_id_factory=lambda: next(attempt_ids),
    )

    previous = await claims.claim("archive-1", "url-1")
    assert previous is not None

    clock.advance(31)
    current = await claims.claim("archive-1", "url-1")

    assert current is not None
    assert current.attempt_id == "attempt-2"
    assert current.fence == previous.fence + 1

    with pytest.raises(TaskClaimLostError):
        await claims.renew(previous)


async def test_claim_requires_an_open_archive_run() -> None:
    client = new_frontier_client()
    client.runs["archive-1"]["admission"] = {"S": "CLOSED"}
    claims = DynamoDBTaskClaims(
        client=client,
        frontier_table_name="capture_frontier",
        runs_table_name="capture_runs",
        lease_duration=30,
        attempt_id_factory=lambda: "attempt-1",
    )

    claim = await claims.claim("archive-1", "url-1")

    assert claim is None
    assert client.frontier[("archive-1", "url-1")]["state"] == {"S": "PENDING"}


async def test_renewal_extends_the_lease_without_changing_attempt_or_fence() -> None:
    clock = FakeClock()
    client = new_frontier_client()
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

    clock.advance(10)
    renewed = await claims.renew(claim)

    assert renewed.attempt_id == claim.attempt_id
    assert renewed.fence == claim.fence
    assert renewed.task == claim.task
    assert renewed.lease_until > claim.lease_until


async def test_renewal_is_rejected_after_the_archive_run_closes() -> None:
    client = new_frontier_client()
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
        await claims.renew(claim)


async def test_concurrent_claims_have_exactly_one_winner_for_a_page() -> None:
    client = new_frontier_client()
    attempt_ids = iter(f"attempt-{number}" for number in range(20))
    claims = DynamoDBTaskClaims(
        client=client,
        frontier_table_name="capture_frontier",
        runs_table_name="capture_runs",
        lease_duration=30,
        attempt_id_factory=lambda: next(attempt_ids),
    )

    results = await asyncio.gather(
        *(claims.claim("archive-1", "url-1") for _ in range(20))
    )

    acquired = [claim for claim in results if claim is not None]

    assert len(acquired) == 1
    assert acquired[0].fence == 1
