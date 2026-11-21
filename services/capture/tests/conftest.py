from collections.abc import Iterator

import pytest
from mypy_boto3_dynamodb.client import DynamoDBClient
from support.dynamodb import cleanup_dynamodb, new_dynamodb_client, setup_dynamodb
from support.recording import LocalSite, start_local_site


@pytest.fixture
def local_site() -> Iterator[LocalSite]:
    site = start_local_site()

    try:
        yield site
    finally:
        site.stop()


@pytest.fixture
def dynamodb() -> Iterator[DynamoDBClient]:
    client = new_dynamodb_client()

    setup_dynamodb(client)

    try:
        yield client
    finally:
        cleanup_dynamodb(client)
