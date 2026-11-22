from uuid import uuid4

import aio_pika
import pytest
from aio_pika.abc import AbstractRobustConnection

from adapters.messaging.rabbitmq.publisher import (
    CAPTURE_ROUTING_KEY,
    RabbitMQMessagePublisher,
)


@pytest.mark.integration
async def test_publisher_delivers_persistent_message_to_a_real_queue(
    rabbitmq: AbstractRobustConnection,
) -> None:
    publisher = RabbitMQMessagePublisher(rabbitmq)
    consumer_channel = await rabbitmq.channel()
    queue = await consumer_channel.declare_queue(
        f"capture-publisher-test-{uuid4()}",
        exclusive=True,
        auto_delete=True,
    )

    try:
        await publisher.start()
        await queue.bind(publisher.exchange, routing_key=CAPTURE_ROUTING_KEY)

        body = b'{"type":"CapturePage"}'
        await publisher.publish("message-1", body)

        received = await queue.get(timeout=5, fail=True)

        assert received.message_id == "message-1"
        assert received.body == body
        assert received.content_type == "application/json"
        assert received.delivery_mode == aio_pika.DeliveryMode.PERSISTENT
        await received.ack()
    finally:
        await publisher.close()
        await queue.delete()
        await consumer_channel.close()


@pytest.mark.integration
async def test_publisher_rejects_publication_before_startup(
    rabbitmq: AbstractRobustConnection,
) -> None:
    publisher = RabbitMQMessagePublisher(rabbitmq)

    with pytest.raises(RuntimeError, match="has not been started"):
        await publisher.publish("message-1", b"{}")
