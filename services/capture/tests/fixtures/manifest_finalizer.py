import pytest
from mypy_boto3_dynamodb.client import DynamoDBClient
from mypy_boto3_s3.client import S3Client

from adapters.persistence.dynamodb.finalize import DynamoDBManifestFinalizer
from ports.capture import CrawlFinalizer
from ports.clock import Clock


@pytest.fixture
def manifest_finalizer(
    dynamodb: DynamoDBClient,
    s3: S3Client,
    clock: Clock,
) -> CrawlFinalizer:
    return DynamoDBManifestFinalizer(dynamodb, s3, clock=clock)
