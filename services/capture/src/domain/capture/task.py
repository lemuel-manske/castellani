from dataclasses import dataclass
from typing import Protocol
from uuid import uuid4

from .auth import DEFAULT_AUTH_GENERATION
from .capture import CaptureOutcome


class TaskClaimLostError(RuntimeError):
    """Raised when a worker no longer owns the current page-task attempt."""


class InvalidTaskClaimRenewal(ValueError):
    """Raised when a task claim renewal violates ownership or lease invariants."""


def new_attempt_id() -> str:
    return str(uuid4())


@dataclass(frozen=True)
class PageTask:
    """A page admitted to an archive's crawl frontier for capture."""

    archive_id: str
    url_key: str
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

        if self.lease_until <= 0:
            raise ValueError("lease_until must be positive")

    def verify_renewal(self, renewed: "TaskClaim", now: float) -> None:
        if (
            renewed.attempt_id != self.attempt_id
            or renewed.fence != self.fence
            or renewed.task != self.task
            or renewed.lease_until <= max(self.lease_until, now)
        ):
            raise InvalidTaskClaimRenewal("task lease renewal returned an invalid claim")


class TaskRepository(Protocol):
    """Owns page-task persistence and the task's domain lifecycle."""

    async def claim(self, archive_id: str, url_key: str) -> TaskClaim | None: ...

    async def renew(self, claim: TaskClaim) -> TaskClaim: ...

    async def complete(
        self,
        outcome: CaptureOutcome,
    ) -> None: ...

    async def fail(self, claim: TaskClaim, reason_code: str, message: str) -> None: ...

    async def release(self, claim: TaskClaim) -> None: ...

    async def admit_discovered(
        self,
        claim: TaskClaim,
        discovered_urls: tuple[str, ...],
        auth_generation: int = DEFAULT_AUTH_GENERATION,
    ) -> None:
        """Durably account for discoveries before allowing parent completion."""
        ...
