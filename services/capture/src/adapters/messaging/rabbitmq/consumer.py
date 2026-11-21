import asyncio
import json
from typing import cast

import aio_pika
from aio_pika.abc import AbstractIncomingMessage, AbstractRobustConnection

from worker.api import CaptureRunner

from .publisher import CAPTURE_ROUTING_KEY, EXCHANGE_NAME

QUEUE_NAME = "castellani.capture.page"
EXPECTED_MESSAGE_TYPE = "CapturePage"
EXPECTED_MESSAGE_VERSION = 1


def parse_delivery(body: bytes) -> tuple[str, str] | None:
    try:
        decoded: object = json.loads(body)
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None

    if not isinstance(decoded, dict):
        return None

    envelope = cast(dict[str, object], decoded)

    message_id = envelope.get("messageId")
    correlation_id = envelope.get("correlationId")
    occurred_at = envelope.get("occurredAt")

    if (
        not isinstance(message_id, str)
        or not message_id
        or not isinstance(correlation_id, str)
        or not correlation_id
        or envelope.get("type") != EXPECTED_MESSAGE_TYPE
        or type(envelope.get("version")) is not int
        or envelope.get("version") != EXPECTED_MESSAGE_VERSION
        or not isinstance(occurred_at, str)
        or not occurred_at
    ):
        return None

    payload = envelope.get("payload")

    if not isinstance(payload, dict):
        return None

    payload = cast(dict[str, object], payload)

    archive_id = payload.get("archiveId")
    url_key = payload.get("urlKey")

    if not isinstance(archive_id, str) or not archive_id:
        return None

    if not isinstance(url_key, str) or not url_key:
        return None

    return archive_id, url_key


class RabbitMQPageTaskConsumer:
    """Consumes CapturePage commands and delegates execution to the worker."""

    def __init__(self, page_capturer: CaptureRunner) -> None:
        self.process_page = page_capturer

    async def handle(self, message: AbstractIncomingMessage) -> None:
        delivery = parse_delivery(message.body)

        if delivery is None:
            await message.reject(requeue=False)
            return

        archive_id, url_key = delivery

        async with message.process(requeue=True):
            await self.process_page(archive_id, url_key)

    async def run(
        self,
        connection: AbstractRobustConnection,
        exchange_name: str = EXCHANGE_NAME,
        queue_name: str = QUEUE_NAME,
        routing_key: str = CAPTURE_ROUTING_KEY,
    ) -> None:
        channel = await connection.channel()
        await channel.set_qos(prefetch_count=1)

        exchange = await channel.declare_exchange(
            exchange_name,
            aio_pika.ExchangeType.DIRECT,
            durable=True,
        )
        queue = await channel.declare_queue(queue_name, durable=True)
        await queue.bind(exchange, routing_key=routing_key)

        consumer_tag = await queue.consume(self.handle)

        try:
            await asyncio.Event().wait()
        finally:
            await queue.cancel(consumer_tag)
            await channel.close()
