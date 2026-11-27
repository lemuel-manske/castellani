import pytest
from mypy_boto3_s3.client import S3Client

from adapters.artifacts.s3 import S3ArtifactStore
from ports.artifacts import PackageArtifacts


@pytest.fixture
def package_artifacts(s3: S3Client) -> PackageArtifacts:
    return S3ArtifactStore(s3)
