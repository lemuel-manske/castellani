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
from application.capture.page_tasks import PageTaskProcessor
from utils.fn import noop


def capture_page_envelope() -> bytes:
    return json.dumps(
        {
            "messageId": str(uuid4()),
            "correlationId": "archive-consumer-test",
            "type": CAPTURE_PAGE_EVENT,
            "version": 1,
            "occurredAt": "2026-11-24T12:00:00Z",
            "payload": {
                "archiveId": "archive-consumer-test",
                "urlKey": "url-consumer-test",
            },
        }
    ).encode()


async def start_processor(
    rabbitmq: AbstractRobustConnection,
    channel: AbstractChannel,
    body: bytes,
    capture_page: Any,
) -> tuple[RabbitMQPageTaskConsumer, asyncio.Task[None]]:
    queue = await channel.get_queue(CAPTURE_PAGE_QUEUE)
    retry_queue = await channel.get_queue(CAPTURE_PAGE_RETRY_QUEUE)
    dead_queue = await channel.get_queue(CAPTURE_DEAD_QUEUE)

    await queue.purge()
    await retry_queue.purge()
    await dead_queue.purge()

    consumer = RabbitMQPageTaskConsumer(rabbitmq)
    processor = PageTaskProcessor(consumer=consumer, worker=capture_page)
    ready = asyncio.Event()
    task = asyncio.create_task(processor.run(ready=ready))

    await asyncio.wait_for(ready.wait(), timeout=5)

    await publish(channel, body)

    return consumer, task


@pytest.mark.integration
async def test_stop_drains_in_flight_delivery(
    rabbitmq: AbstractRobustConnection,
) -> None:
    started = asyncio.Event()
    release = asyncio.Event()
    completed = asyncio.Event()

    async def capture_page(archive_id: str, url_key: str) -> bool:
        noop(archive_id, url_key)

        started.set()

        await release.wait()

        completed.set()

        return True

    channel = await rabbitmq.channel()

    consumer, task = await start_processor(rabbitmq, channel, capture_page_envelope(), capture_page)

    try:
        await asyncio.wait_for(started.wait(), timeout=5)

        consumer.stop()

        await asyncio.sleep(0.05)

        assert not task.done()

        release.set()

        await asyncio.wait_for(task, timeout=5)

        assert completed.is_set()

        queue = await channel.get_queue(CAPTURE_PAGE_QUEUE)

        assert await queue.get(timeout=0.2, fail=False) is None
    finally:
        if not task.done():
            task.cancel()

            with pytest.raises(asyncio.CancelledError):
                await task

        await channel.close()


async def bounded_stop(task: asyncio.Task[None], timeout: float = 0.2) -> None:
    _done, pending = await asyncio.wait([task], timeout=timeout)

    for remaining in pending:
        remaining.cancel()

    if pending:
        await asyncio.gather(*pending, return_exceptions=True)


@pytest.mark.integration
async def test_stop_bounds_in_flight_delivery(
    rabbitmq: AbstractRobustConnection,
) -> None:
    started = asyncio.Event()

    async def capture_page(archive_id: str, url_key: str) -> bool:
        noop(archive_id, url_key)

        started.set()

        await asyncio.Event().wait()

        return True

    channel = await rabbitmq.channel()
    body = capture_page_envelope()

    consumer, task = await start_processor(rabbitmq, channel, body, capture_page)

    try:
        await asyncio.wait_for(started.wait(), timeout=5)

        consumer.stop()

        await bounded_stop(task)

        assert task.cancelled()

        queue = await channel.get_queue(CAPTURE_PAGE_QUEUE)
        redelivered = await asyncio.wait_for(queue.get(timeout=5, fail=True), timeout=5)

        await redelivered.ack()

        assert redelivered.body == body
    finally:
        if not task.done():
            task.cancel()

            with pytest.raises(asyncio.CancelledError):
                await task

        await channel.close()


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

    consumer = RabbitMQPageTaskConsumer(rabbitmq)
    processor = PageTaskProcessor(consumer=consumer, worker=capture_page)
    task = asyncio.create_task(processor.run(ready=ready))

    publisher = RabbitMQMessagePublisher(rabbitmq)

    message_id = str(uuid4())

    try:
        await asyncio.wait_for(ready.wait(), timeout=5)

        await publisher.start()

        envelope = {
            "messageId": message_id,
            "correlationId": "archive-integration-test",
            "type": CAPTURE_PAGE_EVENT,
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
        task.cancel()

        with pytest.raises(asyncio.CancelledError):
            await task

        await publisher.close()
        await queue.purge()
        await channel.close()


@pytest.mark.integration
async def test_consumer_dead_letters_invalid_envelope(
    rabbitmq: AbstractRobustConnection,
) -> None:
    channel = await rabbitmq.channel()
    body = b'{"type":"CapturePage","version":99}'

    _, task = await start_processor(rabbitmq, channel, body, fail_capture_page)

    dead_queue = await channel.get_queue(CAPTURE_DEAD_QUEUE)

    try:
        received = await asyncio.wait_for(dead_queue.get(timeout=5, fail=True), timeout=5)

        await received.ack()

        assert received.body == body
    finally:
        task.cancel()

        with pytest.raises(asyncio.CancelledError):
            await task

        await dead_queue.purge()
        await channel.close()


@pytest.mark.integration
async def test_consumer_dead_letters_message_after_retry_budget(
    rabbitmq: AbstractRobustConnection,
) -> None:
    channel = await rabbitmq.channel()

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

    queue = await channel.get_queue(CAPTURE_PAGE_QUEUE)
    retry_queue = await channel.get_queue(CAPTURE_PAGE_RETRY_QUEUE)
    dead_queue = await channel.get_queue(CAPTURE_DEAD_QUEUE)

    await queue.purge()
    await retry_queue.purge()
    await dead_queue.purge()

    consumer = RabbitMQPageTaskConsumer(rabbitmq)
    processor = PageTaskProcessor(consumer=consumer, worker=fail_capture_page)
    ready = asyncio.Event()
    task = asyncio.create_task(processor.run(ready=ready))

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

        received = await asyncio.wait_for(dead_queue.get(timeout=5, fail=True), timeout=5)

        await received.ack()

        assert received.body == body
    finally:
        task.cancel()

        with pytest.raises(asyncio.CancelledError):
            await task

        await queue.purge()
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
