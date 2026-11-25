import asyncio
import json
from uuid import uuid4

import pytest
from aio_pika.abc import AbstractRobustConnection

from adapters.messaging.rabbitmq.consumer import RabbitMQPageTaskConsumer
from adapters.messaging.rabbitmq.publisher import RabbitMQMessagePublisher
from adapters.messaging.rabbitmq.topology import CAPTURE_PAGE_QUEUE


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
