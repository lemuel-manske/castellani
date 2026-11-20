from pathlib import Path

from application.contracts import CaptureArtifact, CaptureOutcome
from domain.task import TaskClaim


class FakeRepository:
    def __init__(self, claim: TaskClaim) -> None:
        self.claim_result = claim
        self.failed: tuple[TaskClaim, str, str] | None = None
        self.completed: CaptureOutcome | None = None

    async def claim(self, archive_id: str, url_key: str) -> TaskClaim | None:
        return self.claim_result

    async def renew(self, claim: TaskClaim) -> TaskClaim:
        return claim

    async def complete(self, outcome: CaptureOutcome) -> None:
        self.completed = outcome

    async def fail(self, claim: TaskClaim, reason_code: str, message: str) -> None:
        self.failed = (claim, reason_code, message)

    async def release(self, claim: TaskClaim) -> None:
        return None

    async def admit_discovered(
        self,
        claim: TaskClaim,
        discovered_urls: tuple[str, ...],
    ) -> None:
        return None


class FakeCapacity:
    async def reserve(self, attempt_id: str) -> str | None:
        return "reservation-1"

    async def release(self, attempt_id: str, reservation_id: str) -> None:
        return None


class FailingPageExecutor:
    async def execute(self, url: str, output_dir: Path) -> CaptureArtifact:
        raise RuntimeError("browser capture failed")


class FakeArtifactStore:
    def __init__(self, directory: Path) -> None:
        self.directory = directory
        self.discarded: list[tuple[TaskClaim, Path]] = []

    async def create_attempt_directory(self, claim: TaskClaim) -> Path:
        return self.directory

    async def discard_attempt(self, claim: TaskClaim, directory: Path) -> None:
        self.discarded.append((claim, directory))
