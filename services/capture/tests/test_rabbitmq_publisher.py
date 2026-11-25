import json
from typing import cast

import aio_pika
import pytest
from aio_pika.abc import AbstractRobustConnection

from adapters.messaging.rabbitmq.publisher import (
    RabbitMQMessagePublisher,
)
from topology.messaging import (
    CAPTURE_PAGE_QUEUE,
    CRAWL_COMPLETED_QUEUE,
    PAGE_CAPTURED_QUEUE,
)


@pytest.mark.integration
async def test_publisher_delivers_persistent_message_to_provisioned_queue(
    rabbitmq: AbstractRobustConnection,
) -> None:
    publisher = RabbitMQMessagePublisher(rabbitmq)

    await publisher.start()

    channel = await rabbitmq.channel()
    queue = await channel.get_queue(CAPTURE_PAGE_QUEUE)

    await queue.purge()

    try:
        assert publisher.is_started

        await publisher.publish("message-1", "CapturePage", b'{"type":"CapturePage"}')

        received = await queue.get(timeout=5, fail=True)

        assert received.message_id == "message-1"
        assert received.body == b'{"type":"CapturePage"}'
        assert received.content_type == "application/json"
        assert received.delivery_mode == aio_pika.DeliveryMode.PERSISTENT

        await received.ack()
    finally:
        await queue.purge()
        await channel.close()
        await publisher.close()


@pytest.mark.integration
@pytest.mark.parametrize(
    ("message_type", "queue_name"),
    [
        ("PageCaptured", PAGE_CAPTURED_QUEUE),
        ("CrawlCompleted", CRAWL_COMPLETED_QUEUE),
        ("ArchivePrepared", CRAWL_COMPLETED_QUEUE),
        ("ArchivePublished", CRAWL_COMPLETED_QUEUE),
        ("ArchiveCompensated", CRAWL_COMPLETED_QUEUE),
    ],
)
async def test_publisher_routes_events_to_the_events_exchange(
    rabbitmq: AbstractRobustConnection,
    message_type: str,
    queue_name: str,
) -> None:
    publisher = RabbitMQMessagePublisher(rabbitmq)

    await publisher.start()

    channel = await rabbitmq.channel()
    queue = await channel.get_queue(queue_name)

    await queue.purge()

    try:
        envelope = json.dumps({"type": message_type}).encode()

        await publisher.publish("message-2", message_type, envelope)

        received = await queue.get(timeout=5, fail=True)

        assert received.message_id == "message-2"
        assert received.body == envelope

        await received.ack()
    finally:
        await queue.purge()
        await channel.close()
        await publisher.close()


async def test_publisher_rejects_publication_before_startup() -> None:
    publisher = RabbitMQMessagePublisher(cast(AbstractRobustConnection, object()))

    with pytest.raises(RuntimeError, match="has not been started"):
        await publisher.publish("message-1", "CapturePage", b"{}")
