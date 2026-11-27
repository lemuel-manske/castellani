import pytest
from mypy_boto3_dynamodb.client import DynamoDBClient
from mypy_boto3_s3.client import S3Client

from adapters.artifacts.s3 import S3ArtifactStore
from adapters.persistence.dynamodb.finalize import DynamoDBArchiveFinalizationRepository
from application.capture.archive_finalization import ArchiveManifestFinalizer
from ports.capture import CrawlFinalizer
from ports.clock import Clock


@pytest.fixture
def manifest_finalizer(
    dynamodb: DynamoDBClient,
    s3: S3Client,
    clock: Clock,
) -> CrawlFinalizer:
    return ArchiveManifestFinalizer(
        repository=DynamoDBArchiveFinalizationRepository(dynamodb, clock=clock),
        artifacts=S3ArtifactStore(s3),
    )
