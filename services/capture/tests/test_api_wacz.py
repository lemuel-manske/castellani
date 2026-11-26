from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from mypy_boto3_dynamodb.client import DynamoDBClient
from mypy_boto3_s3.client import S3Client
from support.domain import seed_run, set_run_publication
from support.s3 import put_object

from adapters.persistence.dynamodb.archive import DynamoDBArchiveRetrieval
from capture.api.wacz import router as wacz_router
from topology.buckets import ARCHIVE_ARTIFACTS_BUCKET


@pytest.mark.integration
def test_wacz_endpoint_streams_exact_requested_byte_range(
    dynamodb: DynamoDBClient,
    s3: S3Client,
) -> None:
    archive_id = "archive-1"
    package_key = "packages/archive-1.wacz"
    package = b"PK\x03\x04archive-payload"

    seed_run(dynamodb)
    set_run_publication(dynamodb, package_key=package_key)
    put_object(s3, ARCHIVE_ARTIFACTS_BUCKET, package_key, package)

    retrieval = DynamoDBArchiveRetrieval(
        client=dynamodb,
        s3_client=s3,
        artifact_bucket=ARCHIVE_ARTIFACTS_BUCKET,
    )

    application = FastAPI()
    application.include_router(wacz_router)
    application.state.runtime = SimpleNamespace(archive_retrieval=retrieval)

    with TestClient(application) as client:
        response = client.get(
            f"/archives/{archive_id}/wacz",
            headers={"Range": "bytes=0-3"},
        )

    assert response.status_code == 206
    assert response.headers["content-type"] == "application/wacz"
    assert response.headers["content-length"] == "4"
    assert response.headers["content-range"] == f"bytes 0-3/{len(package)}"
    assert response.content == package[:4]
