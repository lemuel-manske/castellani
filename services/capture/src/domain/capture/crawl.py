from dataclasses import dataclass


@dataclass(frozen=True)
class CrawlStart:
    """An admitted archive run that Capture must seed into its frontier."""

    archive_id: str
    seed_url: str
    max_depth: int
    max_pages: int

    def __post_init__(self) -> None:
        if not self.archive_id:
            raise ValueError("archive_id must not be empty")

        if not self.seed_url:
            raise ValueError("seed_url must not be empty")

        if self.max_depth < 0:
            raise ValueError("max_depth must not be negative")

        if self.max_pages < 1:
            raise ValueError("max_pages must be positive")
