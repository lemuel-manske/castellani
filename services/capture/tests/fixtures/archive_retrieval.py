import pytest
from mypy_boto3_dynamodb.client import DynamoDBClient
from mypy_boto3_s3.client import S3Client

from adapters.artifacts.s3 import S3ArtifactStore
from adapters.persistence.dynamodb.archive import DynamoDBArchiveCatalog
from application.capture.archive_retrieval import ArchiveRetrieval


@pytest.fixture
def archive_retrieval(
    dynamodb: DynamoDBClient,
    s3: S3Client,
) -> ArchiveRetrieval:
    return ArchiveRetrieval(
        catalog=DynamoDBArchiveCatalog(dynamodb),
        artifacts=S3ArtifactStore(s3),
    )
