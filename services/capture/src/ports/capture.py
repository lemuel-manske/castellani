from abc import ABC, abstractmethod

from domain.capture import (
    DEFAULT_AUTH_GENERATION,
    AuthContext,
    CaptureOutcome,
    CaptureReservation,
    CompensationDecision,
    OutboxMessage,
    PageListing,
    PendingPackage,
    PreparedPackage,
    PublicationDecision,
    SnapshotReference,
    StartCrawl,
    TaskClaim,
    WACZObject,
)


class CrawlStarter(ABC):
    @abstractmethod
    async def __call__(self, start: StartCrawl) -> None: ...


class CrawlFinalizer(ABC):
    @abstractmethod
    async def __call__(self, archive_id: str) -> None: ...


class CaptureAllocator(ABC):
    """Controls the number of page captures running concurrently."""

    @abstractmethod
    async def reserve(self, attempt_id: str) -> CaptureReservation | None: ...

    @abstractmethod
    async def renew(self, reservation: CaptureReservation) -> CaptureReservation: ...

    @abstractmethod
    async def release(self, reservation: CaptureReservation) -> None: ...


class AuthContextStore(ABC):
    @abstractmethod
    async def load(self, archive_id: str) -> AuthContext: ...


class ArchiveRetrieval(ABC):
    @abstractmethod
    async def list_pages(
        self,
        archive_id: str,
        limit: int,
        cursor: str | None,
    ) -> PageListing: ...

    @abstractmethod
    async def read_snapshot(
        self,
        archive_id: str,
        snapshot_id: str,
    ) -> SnapshotReference | None: ...

    @abstractmethod
    async def read_wacz(
        self,
        archive_id: str,
        range_header: str | None,
        if_range: str | None,
        metadata_only: bool = False,
    ) -> WACZObject | None: ...


class OutboxRepository(ABC):
    """Claims and records delivery of durable outbox messages."""

    @abstractmethod
    async def claim(self, lease_duration: float) -> OutboxMessage | None: ...

    @abstractmethod
    async def confirm(self, message: OutboxMessage) -> None: ...

    @abstractmethod
    async def reschedule(self, message: OutboxMessage, delay: float) -> None: ...


class ArchivePublicationRepository(ABC):
    """Manages the lifecycle of packages and their publication to the archive."""

    @abstractmethod
    async def claim_package(self, lease_duration: float) -> PendingPackage | None: ...

    @abstractmethod
    async def release_package(self, pending: PendingPackage) -> None: ...

    @abstractmethod
    async def prepare(self, prepared: PreparedPackage) -> None: ...

    @abstractmethod
    async def accept_publication(self, decision: PublicationDecision) -> None: ...

    @abstractmethod
    async def begin_compensation(self, decision: CompensationDecision) -> None: ...

    @abstractmethod
    async def complete_compensation(self, decision: CompensationDecision) -> None: ...


class TaskRepository(ABC):
    """Owns page-task persistence and the task's domain lifecycle."""

    @abstractmethod
    async def claim(self, archive_id: str, url_key: str) -> TaskClaim | None: ...

    @abstractmethod
    async def renew(self, claim: TaskClaim) -> TaskClaim: ...

    @abstractmethod
    async def complete(self, outcome: CaptureOutcome) -> None: ...

    @abstractmethod
    async def fail(self, claim: TaskClaim, reason_code: str, message: str) -> None: ...

    @abstractmethod
    async def release(self, claim: TaskClaim) -> None: ...

    @abstractmethod
    async def admit_discovered(
        self,
        claim: TaskClaim,
        discovered_urls: tuple[str, ...],
        auth_generation: int = DEFAULT_AUTH_GENERATION,
    ) -> None: ...
