import pytest
from mypy_boto3_dynamodb.client import DynamoDBClient

from adapters.persistence.dynamodb import outbox
from ports.capture import OutboxRepository
from ports.clock import Clock


@pytest.fixture
def outbox_repository(
    dynamodb: DynamoDBClient,
    clock: Clock,
    deterministic_lease_tokens: None,
) -> OutboxRepository:
    return outbox.DynamoDBOutbox(
        dynamodb,
        clock=clock,
        lease_token_factory=outbox.new_lease_token,
    )
