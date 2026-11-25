import asyncio
import json
from typing import Any
from uuid import uuid4

import aio_pika
import pytest
from aio_pika.abc import AbstractChannel, AbstractRobustConnection

from adapters.messaging.rabbitmq.consumer import RabbitMQPageTaskConsumer
from adapters.messaging.rabbitmq.publisher import RabbitMQMessagePublisher
from adapters.messaging.rabbitmq.topology import (
    CAPTURE_DEAD_QUEUE,
    CAPTURE_EXCHANGE_NAME,
    CAPTURE_PAGE_EVENT,
    CAPTURE_PAGE_QUEUE,
    CAPTURE_PAGE_RETRY_QUEUE,
    MAX_DELIVERY_RETRIES,
)
from utils.fn import noop


@pytest.mark.integration
async def test_consumer_receives_capture_page_from_rabbitmq(
    rabbitmq: AbstractRobustConnection,
) -> None:
    processed = asyncio.Event()

    received: list[tuple[str, str]] = []

    async def capture_page(archive_id: str, url_key: str) -> bool:
        received.append((archive_id, url_key))
        processed.set()
        return True

    ready = asyncio.Event()

    channel = await rabbitmq.channel()
    queue = await channel.get_queue(CAPTURE_PAGE_QUEUE)

    await queue.purge()

    consumer = RabbitMQPageTaskConsumer(capture_page)
    consumer_task = asyncio.create_task(consumer.run(rabbitmq, ready=ready))

    publisher = RabbitMQMessagePublisher(rabbitmq)

    message_id = str(uuid4())

    try:
        await asyncio.wait_for(ready.wait(), timeout=5)

        await publisher.start()

        envelope = {
            "messageId": message_id,
            "correlationId": "archive-integration-test",
            "type": "CapturePage",
            "version": 1,
            "occurredAt": "2026-11-20T12:00:00Z",
            "payload": {
                "archiveId": "archive-integration-test",
                "urlKey": "url-integration-test",
            },
        }

        await publisher.publish(message_id, json.dumps(envelope).encode())

        await asyncio.wait_for(processed.wait(), timeout=5)

        assert received == [("archive-integration-test", "url-integration-test")]
    finally:
        consumer_task.cancel()

        with pytest.raises(asyncio.CancelledError):
            await consumer_task

        await publisher.close()
        await queue.purge()
        await channel.close()


@pytest.mark.integration
async def test_consumer_dead_letters_invalid_envelope(
    rabbitmq: AbstractRobustConnection,
) -> None:
    channel = await rabbitmq.channel()

    page_queue = await channel.get_queue(CAPTURE_PAGE_QUEUE)
    retry_queue = await channel.get_queue(CAPTURE_PAGE_RETRY_QUEUE)
    dead_queue = await channel.get_queue(CAPTURE_DEAD_QUEUE)

    await page_queue.purge()
    await retry_queue.purge()
    await dead_queue.purge()

    ready = asyncio.Event()

    consumer = RabbitMQPageTaskConsumer(fail_capture_page)
    consumer_task = asyncio.create_task(consumer.run(rabbitmq, ready=ready))

    body = b'{"type":"CapturePage","version":99}'

    try:
        await asyncio.wait_for(ready.wait(), timeout=5)

        await publish(channel, body)

        received = await asyncio.wait_for(
            dead_queue.get(timeout=5, fail=True),
            timeout=5,
        )

        await received.ack()

        assert received.body == body
    finally:
        consumer_task.cancel()

        with pytest.raises(asyncio.CancelledError):
            await consumer_task

        await page_queue.purge()
        await retry_queue.purge()
        await dead_queue.purge()
        await channel.close()


@pytest.mark.integration
async def test_consumer_dead_letters_message_after_retry_budget(
    rabbitmq: AbstractRobustConnection,
) -> None:
    channel = await rabbitmq.channel()

    page_queue = await channel.get_queue(CAPTURE_PAGE_QUEUE)
    retry_queue = await channel.get_queue(CAPTURE_PAGE_RETRY_QUEUE)
    dead_queue = await channel.get_queue(CAPTURE_DEAD_QUEUE)

    await page_queue.purge()
    await retry_queue.purge()
    await dead_queue.purge()

    ready = asyncio.Event()

    consumer = RabbitMQPageTaskConsumer(fail_capture_page)
    consumer_task = asyncio.create_task(consumer.run(rabbitmq, ready=ready))

    envelope = {
        "messageId": str(uuid4()),
        "correlationId": "archive-retry-test",
        "type": CAPTURE_PAGE_EVENT,
        "version": 1,
        "occurredAt": "2026-11-24T12:00:00Z",
        "payload": {
            "archiveId": "archive-retry-test",
            "urlKey": "url-retry-test",
        },
    }

    body = json.dumps(envelope).encode()

    try:
        await asyncio.wait_for(ready.wait(), timeout=5)

        await publish(
            channel,
            body,
            headers={
                "x-death": [
                    {
                        "queue": CAPTURE_PAGE_RETRY_QUEUE,
                        "count": MAX_DELIVERY_RETRIES,
                    }
                ]
            },
        )

        received = await asyncio.wait_for(
            dead_queue.get(timeout=5, fail=True),
            timeout=5,
        )

        await received.ack()

        assert received.body == body
    finally:
        consumer_task.cancel()

        with pytest.raises(asyncio.CancelledError):
            await consumer_task

        await page_queue.purge()
        await retry_queue.purge()
        await dead_queue.purge()
        await channel.close()


async def fail_capture_page(archive_id: str, url_key: str) -> bool:
    noop(archive_id, url_key)

    raise AssertionError()


async def publish(
    channel: AbstractChannel,
    body: bytes,
    headers: dict[str, Any] | None = None,
) -> None:
    exchange = await channel.get_exchange(CAPTURE_EXCHANGE_NAME)

    await exchange.publish(
        aio_pika.Message(
            body=body,
            headers=headers,
            content_type="application/json",
            delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
        ),
        routing_key=CAPTURE_PAGE_EVENT,
        mandatory=True,
    )
