import asyncio
import shutil
from pathlib import Path

from domain import TaskClaim
from worker import ArtifactStore


class LocalArtifactStore(ArtifactStore):
    """Stores each capture attempt in a directory named by its immutable attempt ID."""

    def __init__(self, root: Path) -> None:
        self.root = root

    async def create_attempt_directory(self, claim: TaskClaim) -> Path:
        directory = self.root / claim.attempt_id

        await asyncio.to_thread(directory.mkdir, parents=True, exist_ok=True)

        return directory

    async def discard_attempt(self, claim: TaskClaim, directory: Path) -> None:
        del claim

        await asyncio.to_thread(shutil.rmtree, directory, True)
