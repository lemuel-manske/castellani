import asyncio
from collections.abc import AsyncGenerator
from contextlib import aclosing
from typing import Protocol

from domain.capture import CrawlStarter, StartCrawl, is_supported_normalizer_version


class StartCrawlMessage(Protocol):
    """A validated StartCrawl delivery with broker-agnostic outcome operations."""

    archive_id: str
    seed_url: str
    max_depth: int
    max_pages: int
    collection_id: str | None
    allowed_origins: tuple[str, ...]
    auth_generation: int | None
    normalizer_version: str | None
    retry_exhausted: bool

    async def ack(self) -> None: ...

    async def reject(self) -> None: ...

    async def dead_letter(self) -> None: ...


class StartCrawlConsumer(Protocol):
    """Source of validated StartCrawl deliveries."""

    def messages(
        self,
        ready: asyncio.Event | None = None,
    ) -> AsyncGenerator[StartCrawlMessage]: ...

    def stop(self) -> None: ...


class StartCrawlProcessor:
    """Drives validated StartCrawl deliveries through a crawl starter."""

    def __init__(self, consumer: StartCrawlConsumer, starter: CrawlStarter) -> None:
        self.consumer = consumer
        self.starter = starter

    async def run(self, ready: asyncio.Event | None = None) -> None:
        async with aclosing(self.consumer.messages(ready=ready)) as messages:
            async for message in messages:
                if message.retry_exhausted:
                    await message.dead_letter()

                    continue

                if not is_supported_normalizer_version(message.normalizer_version):
                    await message.dead_letter()

                    continue

                start = StartCrawl(
                    archive_id=message.archive_id,
                    seed_url=message.seed_url,
                    max_depth=message.max_depth,
                    max_pages=message.max_pages,
                    collection_id=message.collection_id,
                    allowed_origins=message.allowed_origins,
                    auth_generation=message.auth_generation,
                    normalizer_version=message.normalizer_version,
                )

                try:
                    await self.starter(start)
                except Exception:
                    await message.reject()

                    continue

                await message.ack()
