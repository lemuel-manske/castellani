import pytest
from mypy_boto3_dynamodb.client import DynamoDBClient
from mypy_boto3_s3.client import S3Client

from adapters.persistence.dynamodb.archive import DynamoDBArchiveRetrieval
from ports.capture import ArchiveRetrieval


@pytest.fixture
def archive_retrieval(
    dynamodb: DynamoDBClient,
    s3: S3Client,
) -> ArchiveRetrieval:
    return DynamoDBArchiveRetrieval(dynamodb, s3)
