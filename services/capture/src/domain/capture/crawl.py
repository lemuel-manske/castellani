from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class StartCrawl:
    archive_id: str
    seed_url: str
    max_depth: int
    max_pages: int
    collection_id: str | None = None
    allowed_origins: tuple[str, ...] = ()
    auth_generation: int | None = None
    normalizer_version: str | None = None


class CrawlStarter(Protocol):
    async def __call__(self, start: StartCrawl) -> None: ...


class CrawlFinalizer(Protocol):
    async def __call__(self, archive_id: str) -> None: ...
