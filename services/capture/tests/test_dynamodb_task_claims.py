import asyncio

import pytest
from mypy_boto3_dynamodb.client import DynamoDBClient
from support.clock import Clock
from support.domain import (
    frontier_item,
    seed_frontier,
    seed_run,
    set_run_admission,
)

from adapters.persistence.dynamodb.task import (
    DynamoDBTaskRepository,
    TaskClaimLostError,
)


@pytest.mark.integration
async def test_claim_sets_new_fence_for_pending_task(
    dynamodb: DynamoDBClient, clock: Clock
) -> None:
    seed_run(dynamodb)

    seed_frontier(dynamodb, depth=2)

    claims = DynamoDBTaskRepository(
        client=dynamodb,
        lease_duration=30,
        clock=clock,
    )

    claim = await claims.claim("archive-1", "url-1")
    assert claim is not None

    assert claim.task.url == "https://example.org/"
    assert claim.task.depth == 2
    assert claim.attempt_id == "attempt-1"
    assert claim.fence == 1
    assert claim.lease_until == clock() + 30


@pytest.mark.integration
async def test_claim_does_not_replace_an_active_attempt(dynamodb: DynamoDBClient) -> None:
    seed_run(dynamodb)

    seed_frontier(dynamodb, depth=2)

    claims = DynamoDBTaskRepository(
        client=dynamodb,
        lease_duration=30,
    )

    first = await claims.claim("archive-1", "url-1")
    assert first is not None

    second = await claims.claim("archive-1", "url-1")
    assert second is None

    assert frontier_item(dynamodb)["attemptId"] == {"S": "attempt-1"}


@pytest.mark.integration
async def test_expired_claim_is_reclaimed_with_a_higher_fence(
    dynamodb: DynamoDBClient,
    clock: Clock,
) -> None:
    seed_run(dynamodb)

    seed_frontier(dynamodb, depth=2)

    claims = DynamoDBTaskRepository(
        client=dynamodb,
        lease_duration=30,
        clock=clock,
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


@pytest.mark.integration
async def test_claim_requires_an_open_archive_run(dynamodb: DynamoDBClient) -> None:
    seed_run(dynamodb, admission="CLOSED")

    seed_frontier(dynamodb, depth=2)

    claims = DynamoDBTaskRepository(
        client=dynamodb,
        lease_duration=30,
    )

    claim = await claims.claim("archive-1", "url-1")
    assert claim is None

    assert frontier_item(dynamodb)["state"] == {"S": "PENDING"}


@pytest.mark.integration
async def test_renewal_extends_lease_preserving_owner_and_fence(
    dynamodb: DynamoDBClient, clock: Clock
) -> None:
    seed_run(dynamodb)

    seed_frontier(dynamodb, depth=2)

    claims = DynamoDBTaskRepository(
        client=dynamodb,
        lease_duration=30,
        clock=clock,
    )

    claim = await claims.claim("archive-1", "url-1")
    assert claim is not None

    clock.advance(10)

    renewed = await claims.renew(claim)

    assert renewed.attempt_id == claim.attempt_id
    assert renewed.fence == claim.fence
    assert renewed.task == claim.task
    assert renewed.lease_until > claim.lease_until


@pytest.mark.integration
async def test_renewal_is_rejected_after_the_archive_run_closes(
    dynamodb: DynamoDBClient,
) -> None:
    seed_run(dynamodb)

    seed_frontier(dynamodb, depth=2)

    claims = DynamoDBTaskRepository(
        client=dynamodb,
        lease_duration=30,
    )

    claim = await claims.claim("archive-1", "url-1")
    assert claim is not None

    set_run_admission(dynamodb, "CLOSED")

    with pytest.raises(TaskClaimLostError):
        await claims.renew(claim)


@pytest.mark.integration
async def test_concurrent_claims_have_exactly_one_winner_for_a_page(
    dynamodb: DynamoDBClient,
) -> None:
    seed_run(dynamodb)

    seed_frontier(dynamodb, depth=2)

    claims = DynamoDBTaskRepository(
        client=dynamodb,
        lease_duration=30,
    )

    results = await asyncio.gather(*(claims.claim("archive-1", "url-1") for _ in range(20)))

    acquired = [claim for claim in results if claim is not None]

    assert len(acquired) == 1
    assert acquired[0].fence == 1
