import asyncio
from abc import ABC, abstractmethod
from collections.abc import AsyncGenerator
from typing import Protocol


class MessagePublisher(ABC):
    @abstractmethod
    async def publish(self, message_id: str, message_type: str, envelope: bytes) -> None: ...


class PageTaskMessage(Protocol):
    archive_id: str
    url_key: str
    retry_exhausted: bool

    async def ack(self) -> None: ...

    async def reject(self) -> None: ...

    async def dead_letter(self) -> None: ...


class PageTaskConsumer(ABC):
    @abstractmethod
    def messages(
        self,
        ready: asyncio.Event | None = None,
    ) -> AsyncGenerator[PageTaskMessage]: ...

    @abstractmethod
    def stop(self) -> None: ...


class StartCrawlMessage(Protocol):
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


class StartCrawlConsumer(ABC):
    @abstractmethod
    def messages(
        self,
        ready: asyncio.Event | None = None,
    ) -> AsyncGenerator[StartCrawlMessage]: ...

    @abstractmethod
    def stop(self) -> None: ...


class ArchivePublicationMessage(Protocol):
    archive_id: str
    correlation_id: str
    decision_version: int
    package_digest: str
    occurred_at: str
    retry_exhausted: bool

    async def ack(self) -> None: ...

    async def reject(self) -> None: ...

    async def dead_letter(self) -> None: ...


class ArchivePublicationConsumer(ABC):
    @abstractmethod
    def messages(
        self,
        ready: asyncio.Event | None = None,
    ) -> AsyncGenerator[ArchivePublicationMessage]: ...

    @abstractmethod
    def stop(self) -> None: ...


class ArchiveCompensationMessage(Protocol):
    archive_id: str
    correlation_id: str
    decision_version: int
    reason_code: str
    occurred_at: str
    retry_exhausted: bool

    async def ack(self) -> None: ...

    async def reject(self) -> None: ...

    async def dead_letter(self) -> None: ...


class ArchiveCompensationConsumer(ABC):
    @abstractmethod
    def messages(
        self,
        ready: asyncio.Event | None = None,
    ) -> AsyncGenerator[ArchiveCompensationMessage]: ...

    @abstractmethod
    def stop(self) -> None: ...
