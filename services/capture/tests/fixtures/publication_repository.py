import pytest
from mypy_boto3_dynamodb.client import DynamoDBClient

from adapters.persistence.dynamodb.publication import DynamoDBArchivePublicationRepository
from ports.capture import ArchivePublicationRepository
from ports.clock import Clock


@pytest.fixture
def publication_repository(
    dynamodb: DynamoDBClient,
    clock: Clock,
    deterministic_package_owners: None,
) -> ArchivePublicationRepository:
    return DynamoDBArchivePublicationRepository(dynamodb, clock=clock)
