import asyncio
from typing import cast

from aio_pika.abc import (
    AbstractIncomingMessage,
    AbstractQueue,
    AbstractRobustConnection,
)

from adapters.messaging.contracts import validate_message
from adapters.messaging.types import JSON
from capture.worker.api import CaptureRunner

from .topology import CAPTURE_PAGE_EVENT, CAPTURE_PAGE_QUEUE


class RabbitMQPageTaskConsumer:
    """Consumes CapturePage commands and delegates execution to the worker."""

    def __init__(self, page_capturer: CaptureRunner) -> None:
        self.process_page = page_capturer

    async def handle(self, message: AbstractIncomingMessage) -> None:
        envelope = validate_message(message.body, CAPTURE_PAGE_EVENT)

        if envelope is None:
            await message.reject(requeue=False)

            return

        payload = cast(JSON, envelope["payload"])
        archive_id = cast(str, payload["archiveId"])
        url_key = cast(str, payload["urlKey"])

        async with message.process(requeue=True):
            await self.process_page(archive_id, url_key)

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

            consumer_tag = await queue.consume(self.handle)

            if ready is not None:
                ready.set()

            await asyncio.Event().wait()
        finally:
            try:
                if queue is not None and consumer_tag is not None:
                    await queue.cancel(consumer_tag)
            finally:
                await channel.close()
