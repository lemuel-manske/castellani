import asyncio
import json
from datetime import UTC, datetime
from typing import Any
from uuid import NAMESPACE_URL, uuid5

import aio_pika
import pytest
from aio_pika.abc import AbstractChannel, AbstractRobustConnection
from mypy_boto3_dynamodb.client import DynamoDBClient
from support.clock import Clock
from support.domain import frontier_item, outbox_item, outbox_items, run_item

from adapters.messaging.rabbitmq.consumer import RabbitMQStartCrawlConsumer
from adapters.persistence.dynamodb.run import DynamoDBRunStarter
from application.capture.start_crawls import StartCrawlProcessor
from domain.capture import StartCrawl, identify_url
from ports.capture import CrawlStarter
from topology.messaging import (
    CAPTURE_DEAD_QUEUE,
    CAPTURE_PAGE_QUEUE,
    EVENTS_EXCHANGE_NAME,
    START_CRAWL_EVENT,
    START_CRAWL_QUEUE,
    START_CRAWL_RETRY_QUEUE,
)

ARCHIVE_ID = "archive-start-integration"
COLLECTION_ID = "collection-start"
MESSAGE_ID = "message-start-integration"

SEED_URL = "https://example.org/"
IDENTITY = identify_url(SEED_URL)

ALLOWED_ORIGINS = ["https://example.org"]

NORMALIZER_VERSION = "v1"

AUTH_GENERATION = 3

SEED_MESSAGE_ID = str(
    uuid5(
        NAMESPACE_URL,
        f"capture-page:{ARCHIVE_ID}:{IDENTITY.url_key}",
    )
)

CLOCK_NOW = 1_800_000_000.0

OCCURRED_AT = datetime.fromtimestamp(CLOCK_NOW, UTC).isoformat().replace("+00:00", "Z")


@pytest.mark.integration
async def test_start_crawl_seeds_run_frontier_and_outbox(
    dynamodb: DynamoDBClient,
    rabbitmq: AbstractRobustConnection,
    clock: Clock,
) -> None:
    starter = CountingStarter(DynamoDBRunStarter(client=dynamodb, clock=clock))
    consumer, task, channel = await start_processor(rabbitmq, starter)

    try:
        await publish(channel, start_crawl_envelope())

        await asyncio.wait_for(starter.called.wait(), timeout=5)

        assert (
            run_item(dynamodb, ARCHIVE_ID),
            frontier_item(dynamodb, IDENTITY.url_key, ARCHIVE_ID),
            outbox_item(dynamodb, SEED_MESSAGE_ID),
        ) == (expected_run(), expected_frontier(), expected_outbox())
    finally:
        consumer.stop()
        await task
        await purge_queues(channel)
        await channel.close()


@pytest.mark.integration
async def test_start_crawl_dead_letters_unsupported_normalizer_version(
    dynamodb: DynamoDBClient,
    rabbitmq: AbstractRobustConnection,
    clock: Clock,
) -> None:
    starter = CountingStarter(DynamoDBRunStarter(client=dynamodb, clock=clock))
    consumer, task, channel = await start_processor(rabbitmq, starter)
    envelope = json.loads(start_crawl_envelope())
    envelope["payload"]["normalizerVersion"] = "v2"

    try:
        await publish(channel, json.dumps(envelope).encode())

        dead = await channel.get_queue(CAPTURE_DEAD_QUEUE)

        received = await dead.get(timeout=5, fail=True)

        assert json.loads(received.body)["payload"]["normalizerVersion"] == "v2"

        assert starter.calls == 0
    finally:
        consumer.stop()
        await task
        await purge_queues(channel)
        await channel.close()


@pytest.mark.integration
async def test_start_crawl_redelivery_keeps_one_seed_task(
    dynamodb: DynamoDBClient,
    rabbitmq: AbstractRobustConnection,
    clock: Clock,
) -> None:
    starter = CountingStarter(DynamoDBRunStarter(client=dynamodb, clock=clock))
    consumer, task, channel = await start_processor(rabbitmq, starter)
    body = start_crawl_envelope()

    try:
        await publish(channel, body)
        await publish(channel, body)

        await asyncio.wait_for(wait_for_calls(starter), timeout=5)

        assert (
            run_item(dynamodb, ARCHIVE_ID),
            frontier_item(dynamodb, IDENTITY.url_key, ARCHIVE_ID),
            outbox_items(dynamodb),
        ) == (expected_run(), expected_frontier(), [expected_outbox()])
    finally:
        consumer.stop()
        await task
        await purge_queues(channel)
        await channel.close()


async def start_processor(
    rabbitmq: AbstractRobustConnection,
    starter: CrawlStarter,
) -> tuple[RabbitMQStartCrawlConsumer, asyncio.Task[None], AbstractChannel]:
    channel = await rabbitmq.channel()

    await purge_queues(channel)

    consumer = RabbitMQStartCrawlConsumer(rabbitmq)
    processor = StartCrawlProcessor(consumer=consumer, starter=starter)
    ready = asyncio.Event()
    task = asyncio.create_task(processor.run(ready=ready))

    await asyncio.wait_for(ready.wait(), timeout=5)

    return consumer, task, channel


def start_crawl_envelope() -> bytes:
    return json.dumps(
        {
            "messageId": MESSAGE_ID,
            "correlationId": ARCHIVE_ID,
            "type": START_CRAWL_EVENT,
            "version": 1,
            "occurredAt": "2026-11-25T12:00:00Z",
            "payload": {
                "archiveId": ARCHIVE_ID,
                "seedUrl": SEED_URL,
                "maxDepth": 2,
                "maxPages": 5,
                "collectionId": COLLECTION_ID,
                "allowedOrigins": ALLOWED_ORIGINS,
                "authGeneration": AUTH_GENERATION,
                "normalizerVersion": NORMALIZER_VERSION,
            },
        }
    ).encode()


def expected_run() -> dict[str, Any]:
    return {
        "archiveId": {"S": ARCHIVE_ID},
        "admission": {"S": "OPEN"},
        "seedUrl": {"S": SEED_URL},
        "maxDepth": {"N": "2"},
        "maxPages": {"N": "5"},
        "admittedPages": {"N": "1"},
        "outstandingPages": {"N": "1"},
        "completedPages": {"N": "0"},
        "failedPages": {"N": "0"},
        "collectionId": {"S": COLLECTION_ID},
        "allowedOrigins": {"SS": ALLOWED_ORIGINS},
        "authGeneration": {"N": str(AUTH_GENERATION)},
        "normalizerVersion": {"S": NORMALIZER_VERSION},
        "createdAt": {"S": OCCURRED_AT},
        "updatedAt": {"S": OCCURRED_AT},
    }


def expected_frontier() -> dict[str, Any]:
    return {
        "archiveId": {"S": ARCHIVE_ID},
        "urlKey": {"S": IDENTITY.url_key},
        "url": {"S": IDENTITY.navigation_url},
        "navigationUrl": {"S": IDENTITY.navigation_url},
        "fetchUrl": {"S": IDENTITY.fetch_url},
        "discoveryUrl": {"S": IDENTITY.discovery_url},
        "identityVersion": {"N": "1"},
        "depth": {"N": "0"},
        "state": {"S": "PENDING"},
    }


def expected_outbox() -> dict[str, Any]:
    return {
        "messageId": {"S": SEED_MESSAGE_ID},
        "correlationId": {"S": ARCHIVE_ID},
        "type": {"S": "CapturePage"},
        "version": {"N": "1"},
        "occurredAt": {"S": OCCURRED_AT},
        "payload": {
            "M": {
                "archiveId": {"S": ARCHIVE_ID},
                "urlKey": {"S": IDENTITY.url_key},
            }
        },
        "status": {"S": "PENDING"},
        "attempts": {"N": "0"},
        "nextAttemptAt": {"N": str(int(CLOCK_NOW))},
    }


async def publish(channel: AbstractChannel, body: bytes) -> None:
    exchange = await channel.get_exchange(EVENTS_EXCHANGE_NAME)

    await exchange.publish(
        aio_pika.Message(
            body=body,
            content_type="application/json",
            delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
        ),
        routing_key=START_CRAWL_EVENT,
        mandatory=True,
    )


async def purge_queues(channel: AbstractChannel) -> None:
    for name in (
        START_CRAWL_QUEUE,
        START_CRAWL_RETRY_QUEUE,
        CAPTURE_DEAD_QUEUE,
        CAPTURE_PAGE_QUEUE,
    ):
        queue = await channel.get_queue(name)
        await queue.purge()


class CountingStarter(CrawlStarter):
    def __init__(self, starter: CrawlStarter) -> None:
        self.starter = starter
        self.calls = 0
        self.called = asyncio.Event()

    async def __call__(self, start: StartCrawl) -> None:
        await self.starter(start)
        self.calls += 1
        self.called.set()


async def wait_for_calls(starter: CountingStarter) -> None:
    while starter.calls < 2:
        await asyncio.sleep(0.01)
