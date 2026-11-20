from dataclasses import dataclass


@dataclass(frozen=True)
class PageTask:
    """A page admitted to an archive's crawl frontier for capture."""

    archive_id: str
    url_key: str  # the "canonical" URL key for the page... It's id, perhaps
    url: str
    depth: int

    def __post_init__(self) -> None:
        if not self.archive_id:
            raise ValueError("archive_id must not be empty")

        if not self.url_key:
            raise ValueError("url_key must not be empty")

        if not self.url:
            raise ValueError("url must not be empty")

        if self.depth < 0:
            raise ValueError("depth must not be negative")


@dataclass(frozen=True)
class TaskClaim:
    """A worker's fenced, time-limited ownership of a page task attempt."""

    task: PageTask

    attempt_id: str

    fence: int
    lease_until: float

    def __post_init__(self) -> None:
        if not self.attempt_id:
            raise ValueError("attempt_id must not be empty")

        if self.fence < 1:
            raise ValueError("fence must be positive")
