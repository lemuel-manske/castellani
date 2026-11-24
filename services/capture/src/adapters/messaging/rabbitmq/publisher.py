import json
from typing import Any

import aio_pika
from aio_pika.abc import AbstractChannel, AbstractExchange, AbstractRobustConnection

from .topology import CAPTURE_EXCHANGE_NAME, CAPTURE_PAGE_EVENT, EVENTS_EXCHANGE_NAME

PUBLISHED_EVENTS = frozenset(
    {
        "PageCaptured",
        "CrawlCompleted",
        "ArchivePrepared",
        "ArchivePublished",
        "ArchiveCompensated",
    }
)


class RabbitMQMessagePublisher:
    """Publishes persistent Capture envelopes with broker confirms."""

    def __init__(self, connection: AbstractRobustConnection) -> None:
        self.connection = connection

        self.channel: AbstractChannel | None = None
        self.exchange: AbstractExchange | None = None
        self.events_exchange: AbstractExchange | None = None

    async def start(self) -> None:
        self.channel = await self.connection.channel(
            publisher_confirms=True,
            on_return_raises=True,
        )

        self.exchange = await self.channel.get_exchange(CAPTURE_EXCHANGE_NAME)
        self.events_exchange = await self.channel.get_exchange(EVENTS_EXCHANGE_NAME)

    async def publish(self, message_id: str, envelope: bytes) -> None:
        if self.channel is None or self.exchange is None or self.events_exchange is None:
            raise RuntimeError("RabbitMQ publisher has not been started")

        exchange, routing_key = self.route(envelope)

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

    def route(self, envelope: bytes) -> tuple[AbstractExchange, str]:
        """Commands go to the Capture work exchange; events fan out."""
        message_type: Any = None

        try:
            decoded = json.loads(envelope)
        except (UnicodeDecodeError, json.JSONDecodeError):
            decoded = None

        if isinstance(decoded, dict):
            message_type = decoded.get("type")

        if message_type in PUBLISHED_EVENTS and self.events_exchange is not None:
            return self.events_exchange, str(message_type)

        assert self.exchange is not None

        return self.exchange, CAPTURE_PAGE_EVENT

    async def close(self) -> None:
        if self.channel is not None and not self.channel.is_closed:
            await self.channel.close()

        self.channel = None
        self.exchange = None
        self.events_exchange = None
