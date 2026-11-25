import os
from collections.abc import AsyncIterator, Iterator

import aio_pika
import pytest
from aio_pika.abc import AbstractRobustConnection
from mypy_boto3_dynamodb.client import DynamoDBClient
from mypy_boto3_s3.client import S3Client
from support.clock import Clock
from support.dynamodb import cleanup_dynamodb, new_dynamodb_client, setup_dynamodb
from support.recording import LocalSite, start_local_site
from support.s3 import cleanup_s3, new_s3_client, setup_s3


@pytest.fixture
def clock() -> Iterator[Clock]:
    clock = Clock()

    try:
        yield clock
    finally:
        clock.restart()


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


@pytest.fixture
async def rabbitmq() -> AsyncIterator[AbstractRobustConnection]:
    connection = await aio_pika.connect_robust(os.getenv("CAPTURE_RABBITMQ_URL"))

    try:
        yield connection
    finally:
        await connection.close()


@pytest.fixture
def s3() -> Iterator[S3Client]:
    client = new_s3_client()

    setup_s3(client)

    try:
        yield client
    finally:
        cleanup_s3(client)


@pytest.fixture(autouse=True)
def deterministic_attempt_ids(monkeypatch: pytest.MonkeyPatch) -> None:
    from itertools import count

    from adapters.persistence.dynamodb import task

    identifiers = count(1)
    monkeypatch.setattr(task, "new_attempt_id", lambda: f"attempt-{next(identifiers)}")
