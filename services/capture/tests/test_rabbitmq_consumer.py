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


@pytest.mark.integration
async def test_consumer_handles_a_delivery_from_real_rabbitmq(
    rabbitmq: AbstractRobustConnection,
) -> None:
    channel = await rabbitmq.channel()
    exchange = await channel.declare_exchange(
        EXCHANGE_NAME,
        aio_pika.ExchangeType.DIRECT,
        durable=True,
    )
    queue = await channel.declare_queue(
        f"{QUEUE_NAME}.test-{uuid4()}",
        exclusive=True,
        auto_delete=True,
    )
    await queue.bind(exchange, routing_key="CapturePage")

    processed: list[tuple[str, str]] = []

    async def capture(archive_id: str, url_key: str) -> bool:
        processed.append((archive_id, url_key))
        return True

    consumer = RabbitMQPageTaskConsumer(capture)
    envelope = {
        "messageId": str(uuid4()),
        "correlationId": "archive-1",
        "type": "CapturePage",
        "version": 1,
        "occurredAt": "2026-11-20T12:00:00Z",
        "payload": {"archiveId": "archive-1", "urlKey": "url-1"},
    }

    try:
        await exchange.publish(
            aio_pika.Message(
                body=json.dumps(envelope).encode(),
                content_type="application/json",
                delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
            ),
            routing_key="CapturePage",
            mandatory=True,
        )

        delivery = await queue.get(timeout=5, fail=True)
        await consumer.handle(delivery)

        assert processed == [("archive-1", "url-1")]
    finally:
        await queue.delete()
        await channel.close()


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
