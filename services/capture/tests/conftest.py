from collections.abc import Iterator

import pytest
from mypy_boto3_dynamodb.client import DynamoDBClient
from support.clock import FakeClock
from support.dynamodb import cleanup_dynamodb, new_dynamodb_client, setup_dynamodb
from support.rabbitmq import FakeConnection
from support.recording import LocalSite, start_local_site


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
def rabbitmq() -> Iterator[FakeConnection]:
    connection = FakeConnection()

    try:
        yield connection
    finally:
        pass


@pytest.fixture(autouse=True)
def deterministic_attempt_ids(monkeypatch: pytest.MonkeyPatch) -> None:
    from itertools import count

    from adapters.persistence.dynamodb import task

    identifiers = count(1)
    monkeypatch.setattr(task, "new_attempt_id", lambda: f"attempt-{next(identifiers)}")
