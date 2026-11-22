import asyncio
import json
from uuid import uuid4

import pytest
from aio_pika.abc import AbstractRobustConnection

from adapters.messaging.rabbitmq.consumer import (
    QUEUE_NAME,
    RabbitMQPageTaskConsumer,
    parse_delivery,
)
from adapters.messaging.rabbitmq.publisher import RabbitMQMessagePublisher


def test_parse_delivery_extracts_archive_and_url_identity() -> None:
    body = json.dumps(
        {
            "messageId": "message-1",
            "correlationId": "archive-1",
            "type": "CapturePage",
            "version": 1,
            "occurredAt": "2026-11-20T12:00:00Z",
            "payload": {"archiveId": "archive-1", "urlKey": "v1-identity"},
        }
    ).encode()

    assert parse_delivery(body) == ("archive-1", "v1-identity")


def test_parse_delivery_rejects_malformed_or_unsupported_envelopes() -> None:
    assert parse_delivery(b"{") is None
    assert parse_delivery(b"[]") is None

    envelope = {
        "messageId": "message-1",
        "correlationId": "archive-1",
        "type": "CapturePage",
        "version": True,
        "occurredAt": "2026-11-20T12:00:00Z",
        "payload": {"archiveId": "archive-1", "urlKey": "url-1"},
    }

    assert parse_delivery(json.dumps(envelope).encode()) is None


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

    consumer = RabbitMQPageTaskConsumer(capture_page)

    queue_name = f"{QUEUE_NAME}.test-{uuid4()}"
    consumer_task = asyncio.create_task(consumer.run(rabbitmq, queue_name=queue_name, ready=ready))

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

        cleanup_channel = await rabbitmq.channel()

        try:
            queue = await cleanup_channel.declare_queue(queue_name, durable=True)

            await queue.delete()
        finally:
            await cleanup_channel.close()
