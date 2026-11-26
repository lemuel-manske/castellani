import asyncio
from collections.abc import Awaitable, Callable
from contextlib import aclosing

from ports.messaging import PageTaskConsumer


class PageTaskProcessor:
    """Drives validated page-task deliveries through a capture runner."""

    def __init__(
        self,
        consumer: PageTaskConsumer,
        worker: Callable[[str, str], Awaitable[bool]],
    ) -> None:
        self.consumer = consumer
        self.worker = worker

    async def run(self, ready: asyncio.Event | None = None) -> None:
        async with aclosing(self.consumer.messages(ready=ready)) as messages:
            async for message in messages:
                if message.retry_exhausted:
                    await message.dead_letter()

                    continue

                try:
                    await self.worker(message.archive_id, message.url_key)
                except Exception:
                    await message.reject()

                    continue

                await message.ack()
