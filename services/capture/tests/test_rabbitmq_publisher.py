from typing import cast

import aio_pika
import pytest
from support.rabbitmq import FakeConnection

from adapters.messaging.rabbitmq.publisher import (
    CAPTURE_ROUTING_KEY,
    EXCHANGE_NAME,
    RabbitMQMessagePublisher,
)


async def test_publisher_declares_durable_exchange_and_publishes_persistent_message(
    connection: FakeConnection,
) -> None:
    publisher = RabbitMQMessagePublisher(connection)  # type: ignore[arg-type]

    await publisher.start()
    await publisher.publish("message-1", b'{"type":"CapturePage"}')

    assert connection.channel_options == {
        "publisher_confirms": True,
        "on_return_raises": True,
    }
    assert connection.channel_instance.declarations == [
        (EXCHANGE_NAME, aio_pika.ExchangeType.DIRECT, True)
    ]

    message, routing_key, mandatory = connection.channel_instance.exchange.publications[0]
    published = cast(aio_pika.Message, message)

    assert published.message_id == "message-1"
    assert published.body == b'{"type":"CapturePage"}'
    assert published.content_type == "application/json"
    assert published.delivery_mode == aio_pika.DeliveryMode.PERSISTENT
    assert routing_key == CAPTURE_ROUTING_KEY
    assert mandatory

    await publisher.close()

    assert connection.channel_instance.is_closed


async def test_publisher_rejects_publication_before_startup() -> None:
    publisher = RabbitMQMessagePublisher(FakeConnection())  # type: ignore[arg-type]

    with pytest.raises(RuntimeError, match="has not been started"):
        await publisher.publish("message-1", b"{}")
