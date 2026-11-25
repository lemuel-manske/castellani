import asyncio
from collections.abc import AsyncGenerator
from contextlib import aclosing
from typing import Protocol

from capture.worker.api import CaptureRunner


class PageTaskMessage(Protocol):
    """A validated page-task delivery with broker-agnostic outcome operations."""

    archive_id: str
    url_key: str
    retry_exhausted: bool

    async def ack(self) -> None: ...
    async def reject(self) -> None: ...
    async def dead_letter(self) -> None: ...


class PageTaskConsumer(Protocol):
    """Source of validated page-task deliveries."""

    def messages(
        self,
        ready: asyncio.Event | None = None,
    ) -> AsyncGenerator[PageTaskMessage]: ...

    def stop(self) -> None: ...


class PageTaskProcessor:
    """Drives validated page-task deliveries through a capture runner."""

    def __init__(self, consumer: PageTaskConsumer, worker: CaptureRunner) -> None:
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
