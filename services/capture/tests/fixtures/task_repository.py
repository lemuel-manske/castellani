import pytest
from mypy_boto3_dynamodb.client import DynamoDBClient

from adapters.persistence.dynamodb.task import DynamoDBTaskRepository
from ports.capture import TaskRepository
from ports.clock import Clock

LEASE_DURATION = 60.0


@pytest.fixture
def task_repository(
    dynamodb: DynamoDBClient,
    clock: Clock,
    deterministic_attempt_ids: None,
) -> TaskRepository:
    return DynamoDBTaskRepository(
        dynamodb,
        lease_duration=LEASE_DURATION,
        clock=clock,
    )
