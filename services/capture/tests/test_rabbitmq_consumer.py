import asyncio
import json
from uuid import uuid4

import aio_pika
import pytest
from aio_pika.abc import AbstractRobustConnection

from adapters.messaging.rabbitmq.consumer import (
    EXCHANGE_NAME,
    QUEUE_NAME,
    RabbitMQPageTaskConsumer,
    parse_delivery,
)
from adapters.messaging.rabbitmq.publisher import RabbitMQMessagePublisher


@pytest.mark.integration
async def test_consumer_receives_delivery_through_its_real_queue_subscription(
    rabbitmq: AbstractRobustConnection,
) -> None:
    processed: list[tuple[str, str]] = []
    processed_event = asyncio.Event()
    ready = asyncio.Event()

    async def capture(archive_id: str, url_key: str) -> bool:
        processed.append((archive_id, url_key))
        processed_event.set()
        return True

    consumer = RabbitMQPageTaskConsumer(capture)
    queue_name = f"{QUEUE_NAME}.test-{uuid4()}"
    consumer_task = asyncio.create_task(
        consumer.run(
            rabbitmq,
            queue_name=queue_name,
            ready=ready,
        )
    )
    publisher = RabbitMQMessagePublisher(rabbitmq)

    try:
        await asyncio.wait_for(ready.wait(), timeout=5)
        await publisher.start()
        envelope = {
            "messageId": str(uuid4()),
            "correlationId": "archive-1",
            "type": "CapturePage",
            "version": 1,
            "occurredAt": "2026-11-20T12:00:00Z",
            "payload": {"archiveId": "archive-1", "urlKey": "url-1"},
        }

        await publisher.publish(
            envelope["messageId"],
            json.dumps(envelope).encode(),
        )
        await asyncio.wait_for(processed_event.wait(), timeout=5)

        assert processed == [("archive-1", "url-1")]
    finally:
        consumer_task.cancel()

        with pytest.raises(asyncio.CancelledError):
            await consumer_task

        await publisher.close()


@pytest.mark.integration
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


@pytest.mark.integration
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
