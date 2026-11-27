import pytest
from mypy_boto3_dynamodb.client import DynamoDBClient

from adapters.persistence.dynamodb.session import DynamoDBSessionStore
from ports.login import SessionStore

SESSION_TTL_SECONDS = 3600


@pytest.fixture
def session_store(dynamodb: DynamoDBClient) -> SessionStore:
    return DynamoDBSessionStore(
        dynamodb,
        session_ttl_seconds=SESSION_TTL_SECONDS,
    )
