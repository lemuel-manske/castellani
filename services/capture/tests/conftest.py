import os
from collections.abc import Iterator

import aio_pika
import pytest
from aio_pika.abc import AbstractRobustConnection
from mypy_boto3_dynamodb.client import DynamoDBClient
from support.clock import FakeClock
from support.dynamodb import cleanup_dynamodb, new_dynamodb_client, setup_dynamodb
from support.recording import LocalSite, start_local_site
from support.s3 import FakeS3


@pytest.fixture
def clock() -> Iterator[FakeClock]:
    clock = FakeClock()

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
def s3() -> FakeS3:
    return FakeS3()


@pytest.fixture
async def rabbitmq() -> Iterator[AbstractRobustConnection]:
    connection = await aio_pika.connect_robust(
        os.getenv(
            "RABBITMQ_URL",
            "amqp://castellani:castellani@localhost:5672/",
        )
    )

    try:
        yield connection
    finally:
        await connection.close()


@pytest.fixture(autouse=True)
def deterministic_attempt_ids(monkeypatch: pytest.MonkeyPatch) -> None:
    from itertools import count

    from adapters.persistence.dynamodb import task

    identifiers = count(1)
    monkeypatch.setattr(task, "new_attempt_id", lambda: f"attempt-{next(identifiers)}")
