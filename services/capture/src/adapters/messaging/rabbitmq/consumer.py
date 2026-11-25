import asyncio
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
from capture.worker.api import CaptureRunner

from .topology import (
    CAPTURE_DEAD_EXCHANGE,
    CAPTURE_PAGE_EVENT,
    CAPTURE_PAGE_QUEUE,
    CAPTURE_PAGE_RETRY_QUEUE,
    MAX_DELIVERY_RETRIES,
)


class RabbitMQPageTaskConsumer:
    """Consumes CapturePage commands and delegates execution to the worker."""

    def __init__(self, page_capturer: CaptureRunner) -> None:
        self.process_page = page_capturer

    async def handle(
        self,
        channel: AbstractChannel,
        message: AbstractIncomingMessage,
    ) -> None:
        envelope = validate_message(message.body, CAPTURE_PAGE_EVENT)

        if envelope is None or retry_count(message) >= MAX_DELIVERY_RETRIES:
            await publish_dead_letter(channel, message)
            await message.ack()

            return

        payload = cast(JSON, envelope["payload"])
        archive_id = cast(str, payload["archiveId"])
        url_key = cast(str, payload["urlKey"])

        try:
            await self.process_page(archive_id, url_key)
        except Exception:
            await message.reject(requeue=False)

            return

        await message.ack()

    async def run(
        self,
        connection: AbstractRobustConnection,
        queue_name: str = CAPTURE_PAGE_QUEUE,
        ready: asyncio.Event | None = None,
    ) -> None:
        channel = await connection.channel()

        queue: AbstractQueue | None = None

        consumer_tag: str | None = None

        try:
            await channel.set_qos(prefetch_count=1)

            queue = await channel.get_queue(queue_name)

            consumer_tag = await queue.consume(lambda message: self.handle(channel, message))

            if ready is not None:
                ready.set()

            await asyncio.Event().wait()
        finally:
            try:
                if queue is not None and consumer_tag is not None:
                    await queue.cancel(consumer_tag)
            finally:
                await channel.close()


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
