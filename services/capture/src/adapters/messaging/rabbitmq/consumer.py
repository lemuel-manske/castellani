import asyncio
from collections.abc import AsyncGenerator
from typing import cast

import aio_pika
from aio_pika.abc import (
    AbstractChannel,
    AbstractIncomingMessage,
    AbstractQueue,
    AbstractRobustConnection,
)

from adapters.messaging.contracts import validate_message
from adapters.messaging.types import JSON
from application.capture.page_tasks import PageTaskConsumer, PageTaskMessage

from .topology import (
    CAPTURE_DEAD_EXCHANGE,
    CAPTURE_PAGE_EVENT,
    CAPTURE_PAGE_QUEUE,
    CAPTURE_PAGE_RETRY_QUEUE,
    MAX_DELIVERY_RETRIES,
)


class RabbitMQPageTaskMessage(PageTaskMessage):
    """A validated CapturePage delivery exposed through a broker-agnostic API."""

    def __init__(
        self,
        message: AbstractIncomingMessage,
        channel: AbstractChannel,
        archive_id: str,
        url_key: str,
        retry_exhausted: bool,
    ) -> None:
        self._message = message
        self._channel = channel

        self.archive_id = archive_id
        self.url_key = url_key
        self.retry_exhausted = retry_exhausted

    async def ack(self) -> None:
        await self._message.ack()

    async def reject(self) -> None:
        await self._message.reject(requeue=False)

    async def dead_letter(self) -> None:
        await publish_dead_letter(self._channel, self._message)
        await self._message.ack()


class RabbitMQPageTaskConsumer(PageTaskConsumer):
    """Consumes validated CapturePage envelopes from the provisioned queue."""

    def __init__(self, connection: AbstractRobustConnection) -> None:
        self.connection = connection

        self._stopping = asyncio.Event()
        self._deliveries: asyncio.Queue[RabbitMQPageTaskMessage | None] | None = None

    async def messages(
        self,
        ready: asyncio.Event | None = None,
    ) -> AsyncGenerator[RabbitMQPageTaskMessage]:
        channel = await self.connection.channel()

        deliveries: asyncio.Queue[RabbitMQPageTaskMessage | None] = asyncio.Queue()

        if self._stopping.is_set():
            deliveries.put_nowait(None)

        self._deliveries = deliveries

        queue: AbstractQueue | None = None

        consumer_tag: str | None = None

        async def consume(message: AbstractIncomingMessage) -> None:
            envelope = validate_message(message.body, CAPTURE_PAGE_EVENT)

            if envelope is None:
                await publish_dead_letter(channel, message)
                await message.ack()

                return

            payload = cast(JSON, envelope["payload"])

            await deliveries.put(
                RabbitMQPageTaskMessage(
                    message=message,
                    channel=channel,
                    archive_id=cast(str, payload["archiveId"]),
                    url_key=cast(str, payload["urlKey"]),
                    retry_exhausted=retry_count(message) >= MAX_DELIVERY_RETRIES,
                )
            )

        try:
            await channel.set_qos(prefetch_count=1)

            queue = await channel.get_queue(CAPTURE_PAGE_QUEUE)

            consumer_tag = await queue.consume(consume)

            if ready is not None:
                ready.set()

            while (delivery := await deliveries.get()) is not None:
                yield delivery
        finally:
            self._deliveries = None

            try:
                if queue is not None and consumer_tag is not None:
                    await queue.cancel(consumer_tag)
            finally:
                await channel.close()

    def stop(self) -> None:
        self._stopping.set()

        if self._deliveries is not None:
            self._deliveries.put_nowait(None)


def retry_count(message: AbstractIncomingMessage) -> int:
    headers = message.info().get("headers")

    if not isinstance(headers, dict):
        return 0

    deaths = headers.get("x-death")

    if not isinstance(deaths, list | tuple):
        return 0

    count = 0

    for death in deaths:
        if not isinstance(death, dict):
            continue

        if death.get("queue") != CAPTURE_PAGE_RETRY_QUEUE:
            continue

        attempts = death.get("count")

        if isinstance(attempts, int) and not isinstance(attempts, bool):
            count += attempts

    return count


async def publish_dead_letter(
    channel: AbstractChannel,
    message: AbstractIncomingMessage,
) -> None:
    info = message.info()
    exchange = await channel.get_exchange(CAPTURE_DEAD_EXCHANGE)

    await exchange.publish(
        aio_pika.Message(
            body=message.body,
            headers=info.get("headers"),
            content_type=info.get("content_type"),
            delivery_mode=info.get("delivery_mode"),
            correlation_id=info.get("correlation_id"),
            message_id=info.get("message_id"),
            type=info.get("type"),
        ),
        routing_key="",
    )
