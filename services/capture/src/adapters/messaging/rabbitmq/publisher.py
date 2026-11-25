import aio_pika
from aio_pika.abc import AbstractChannel, AbstractExchange, AbstractRobustConnection

from .topology import CAPTURE_EXCHANGE_NAME, CAPTURE_PAGE_EVENT


class RabbitMQMessagePublisher:
    """Publishes persistent Capture command envelopes with broker confirms."""

    def __init__(self, connection: AbstractRobustConnection) -> None:
        self.connection = connection

        self.channel: AbstractChannel | None = None
        self.exchange: AbstractExchange | None = None

    async def start(self) -> None:
        self.channel = await self.connection.channel(
            publisher_confirms=True,
            on_return_raises=True,
        )

        self.exchange = await self.channel.get_exchange(CAPTURE_EXCHANGE_NAME)

    async def publish(self, message_id: str, envelope: bytes) -> None:
        if self.exchange is None:
            raise RuntimeError("RabbitMQ publisher has not been started")

        message = aio_pika.Message(
            body=envelope,
            message_id=message_id,
            content_type="application/json",
            delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
        )

        await self.exchange.publish(
            message,
            routing_key=CAPTURE_PAGE_EVENT,
            mandatory=True,
        )

    async def close(self) -> None:
        if self.channel is not None and not self.channel.is_closed:
            await self.channel.close()

        self.channel = None
        self.exchange = None
