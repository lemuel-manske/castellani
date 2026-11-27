import os
from collections.abc import AsyncIterator, Iterator

import aio_pika
import pytest
from aio_pika.abc import AbstractRobustConnection
from mypy_boto3_dynamodb.client import DynamoDBClient
from mypy_boto3_s3.client import S3Client
from support.clock import SimpleClock
from support.dynamodb import cleanup_dynamodb, new_dynamodb_client, setup_dynamodb
from support.s3 import cleanup_s3, new_s3_client, setup_s3

from config.environment import CAPTURE_RABBITMQ_URL

pytest_plugins = [
    "fixtures.archive_retrieval",
    "fixtures.capture_allocator",
    "fixtures.crawl_starter",
    "fixtures.deterministic_attempt_ids",
    "fixtures.deterministic_lease_tokens",
    "fixtures.deterministic_package_owners",
    "fixtures.manifest_finalizer",
    "fixtures.outbox_repository",
    "fixtures.package_artifacts",
    "fixtures.publication_repository",
    "fixtures.session_store",
    "fixtures.task_repository",
]


@pytest.fixture
def clock() -> Iterator[SimpleClock]:
    clock = SimpleClock()

    try:
        yield clock
    finally:
        clock.restart()


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
    connection = await aio_pika.connect_robust(os.getenv(CAPTURE_RABBITMQ_URL))

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
