import aio_pika
from aio_pika.abc import AbstractChannel, AbstractExchange, AbstractRobustConnection

from ports.messaging import MessagePublisher
from topology.messaging import (
    ARCHIVE_COMPENSATED_EVENT,
    ARCHIVE_PREPARED_EVENT,
    ARCHIVE_PUBLISHED_EVENT,
    CAPTURE_EXCHANGE_NAME,
    CAPTURE_PAGE_EVENT,
    CRAWL_COMPLETED_EVENT,
    EVENTS_EXCHANGE_NAME,
    PAGE_CAPTURED_EVENT,
)

ROUTES = {
    ARCHIVE_COMPENSATED_EVENT: (EVENTS_EXCHANGE_NAME, ARCHIVE_COMPENSATED_EVENT),
    ARCHIVE_PREPARED_EVENT: (EVENTS_EXCHANGE_NAME, ARCHIVE_PREPARED_EVENT),
    ARCHIVE_PUBLISHED_EVENT: (EVENTS_EXCHANGE_NAME, ARCHIVE_PUBLISHED_EVENT),
    CAPTURE_PAGE_EVENT: (CAPTURE_EXCHANGE_NAME, CAPTURE_PAGE_EVENT),
    CRAWL_COMPLETED_EVENT: (EVENTS_EXCHANGE_NAME, CRAWL_COMPLETED_EVENT),
    PAGE_CAPTURED_EVENT: (EVENTS_EXCHANGE_NAME, PAGE_CAPTURED_EVENT),
}


class RabbitMQMessagePublisher(MessagePublisher):
    """Publishes persistent outbox envelopes to their provisioned exchanges."""

    def __init__(self, connection: AbstractRobustConnection) -> None:
        self.connection = connection

        self.channel: AbstractChannel | None = None
        self.capture_exchange: AbstractExchange | None = None
        self.events_exchange: AbstractExchange | None = None

    @property
    def is_started(self) -> bool:
        return (
            self.channel is not None
            and self.capture_exchange is not None
            and self.events_exchange is not None
        )

    async def publish(self, message_id: str, message_type: str, envelope: bytes) -> None:
        if not self.is_started:
            raise RuntimeError("RabbitMQ publisher has not been started")

        if message_type not in ROUTES:
            raise RuntimeError(f"unsupported outbox message type: {message_type}")

        exchange_name, routing_key = ROUTES[message_type]

        exchanges = {
            CAPTURE_EXCHANGE_NAME: self.capture_exchange,
            EVENTS_EXCHANGE_NAME: self.events_exchange,
        }

        exchange = exchanges[exchange_name]

        if exchange is None:
            raise RuntimeError("RabbitMQ publisher has not been started")

        message = aio_pika.Message(
            body=envelope,
            message_id=message_id,
            content_type="application/json",
            delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
        )

        await exchange.publish(
            message,
            routing_key=routing_key,
            mandatory=True,
        )

    async def start(self) -> None:
        self.channel = await self.connection.channel(
            publisher_confirms=True,
            on_return_raises=True,
        )

        self.capture_exchange = await self.channel.get_exchange(CAPTURE_EXCHANGE_NAME)
        self.events_exchange = await self.channel.get_exchange(EVENTS_EXCHANGE_NAME)

    async def close(self) -> None:
        if self.channel is not None and not self.channel.is_closed:
            await self.channel.close()

        self.channel = None
        self.capture_exchange = None
        self.events_exchange = None
