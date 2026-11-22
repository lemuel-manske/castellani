from typing import cast
from uuid import uuid4

import aio_pika
import pytest
from aio_pika.abc import AbstractRobustConnection

from adapters.messaging.rabbitmq.publisher import (
    CAPTURE_ROUTING_KEY,
    RabbitMQMessagePublisher,
)


@pytest.mark.integration
async def test_publisher_delivers_persistent_message_to_bound_queue(
    rabbitmq: AbstractRobustConnection,
) -> None:
    publisher = RabbitMQMessagePublisher(rabbitmq)

    await publisher.start()

    channel = await rabbitmq.channel()

    queue_name = f"capture-publisher-test-{uuid4()}"
    queue = await channel.declare_queue(queue_name, exclusive=True, auto_delete=True)

    try:
        assert publisher.exchange is not None

        await queue.bind(publisher.exchange, routing_key=CAPTURE_ROUTING_KEY)

        await publisher.publish("message-1", b'{"type":"CapturePage"}')

        received = await queue.get(timeout=5, fail=True)

        assert received.message_id == "message-1"
        assert received.body == b'{"type":"CapturePage"}'
        assert received.content_type == "application/json"
        assert received.delivery_mode == aio_pika.DeliveryMode.PERSISTENT

        await received.ack()
    finally:
        await channel.close()
        await publisher.close()


async def test_publisher_rejects_publication_before_startup() -> None:
    publisher = RabbitMQMessagePublisher(cast(AbstractRobustConnection, object()))

    with pytest.raises(RuntimeError, match="has not been started"):
        await publisher.publish("message-1", b"{}")
