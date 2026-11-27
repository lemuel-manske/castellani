from dataclasses import dataclass


class CaptureRunMissing(RuntimeError):
    """Raised when a crawl run that must exist cannot be found."""


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
