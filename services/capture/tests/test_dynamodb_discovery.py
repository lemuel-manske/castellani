import pytest
from mypy_boto3_dynamodb.client import DynamoDBClient
from support.clock import Clock
from support.domain import (
    frontier_item,
    outbox_items,
    run_item,
    seed_frontier,
    seed_run,
    set_run_auth_generation,
)

from adapters.persistence.dynamodb.task import (
    DynamoDBTaskRepository,
    TaskClaimLostError,
)
from domain.capture import AuthGenerationChanged, identify_url


@pytest.mark.integration
async def test_discovery_admission_is_atomic_and_idempotent(
    dynamodb: DynamoDBClient,
    clock: Clock,
) -> None:
    seed_run(dynamodb, max_pages=3, admitted_pages=1)
    seed_frontier(dynamodb)

    repository = DynamoDBTaskRepository(
        client=dynamodb,
        lease_duration=30,
        clock=clock,
    )

    claim = await repository.claim("archive-1", "url-1")
    assert claim is not None

    urls = (
        "https://EXAMPLE.org:443/child",
        "https://example.org/child",
        "https://example.org/child#section",
    )

    await repository.admit_discovered(claim, urls, 0)
    await repository.admit_discovered(claim, urls, 0)

    child = identify_url(urls[0])

    item = frontier_item(dynamodb, child.url_key)

    assert item["navigationUrl"] == {"S": child.navigation_url}
    assert item["fetchUrl"] == {"S": child.fetch_url}
    assert item["depth"] == {"N": "1"}
    assert item["state"] == {"S": "PENDING"}

    run = run_item(dynamodb)

    assert run["admittedPages"] == {"N": "2"}
    assert run["outstandingPages"] == {"N": "2"}

    messages = outbox_items(dynamodb)

    assert len(messages) == 1
    assert messages[0]["payload"]["M"]["urlKey"] == {"S": child.url_key}


@pytest.mark.integration
async def test_discovery_admission_never_exceeds_max_pages(
    dynamodb: DynamoDBClient,
    clock: Clock,
) -> None:
    seed_run(dynamodb, max_pages=1, admitted_pages=1)
    seed_frontier(dynamodb)

    repository = DynamoDBTaskRepository(
        client=dynamodb,
        lease_duration=30,
        clock=clock,
    )

    claim = await repository.claim("archive-1", "url-1")
    assert claim is not None

    await repository.admit_discovered(
        claim,
        ("https://example.org/one", "https://example.org/two"),
        0,
    )

    run = run_item(dynamodb)

    assert run["admittedPages"] == {"N": "1"}
    assert run["outstandingPages"] == {"N": "1"}

    assert outbox_items(dynamodb) == []


@pytest.mark.integration
async def test_discovery_admission_rejects_a_stale_parent_claim(
    dynamodb: DynamoDBClient,
    clock: Clock,
) -> None:
    seed_run(dynamodb)
    seed_frontier(dynamodb)

    repository = DynamoDBTaskRepository(
        client=dynamodb,
        lease_duration=30,
        clock=clock,
    )

    claim = await repository.claim("archive-1", "url-1")
    assert claim is not None

    clock.advance(31)

    with pytest.raises(TaskClaimLostError):
        await repository.admit_discovered(claim, ("https://example.org/child",), 0)

    assert outbox_items(dynamodb) == []


@pytest.mark.integration
async def test_discovery_admission_rejects_a_stale_auth_generation(
    dynamodb: DynamoDBClient,
    clock: Clock,
) -> None:
    seed_run(dynamodb, auth_generation=1)
    seed_frontier(dynamodb)

    repository = DynamoDBTaskRepository(
        client=dynamodb,
        lease_duration=30,
        clock=clock,
    )

    claim = await repository.claim("archive-1", "url-1")

    assert claim is not None

    set_run_auth_generation(dynamodb, 2)

    with pytest.raises(AuthGenerationChanged):
        await repository.admit_discovered(claim, ("https://example.org/child",), 1)

    assert outbox_items(dynamodb) == []
