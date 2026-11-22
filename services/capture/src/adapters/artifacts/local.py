import asyncio
import hashlib
import shutil
from pathlib import Path

from domain import ArtifactReference, TaskClaim
from worker import ArtifactStore


def references(directory: Path, warc_files: tuple[Path, ...]) -> tuple[ArtifactReference, ...]:
    if not warc_files:
        raise ValueError("a capture must produce at least one WARC file")

    references: list[ArtifactReference] = []
    for path in warc_files:
        resolved = path.resolve(strict=True)
        relative = resolved.relative_to(directory.resolve(strict=True))
        if not resolved.is_file():
            raise ValueError(f"capture artifact is not a regular file: {path}")
        digest_builder = hashlib.sha256()
        with resolved.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest_builder.update(chunk)
        references.append(
            ArtifactReference(
                bucket="local",
                key=relative.as_posix(),
                sha256=digest_builder.hexdigest(),
                size_bytes=resolved.stat().st_size,
            )
        )
    return tuple(references)


class LocalArtifactStore(ArtifactStore):
    """Stores immutable attempt artifacts on the local filesystem."""

    def __init__(self, root: Path) -> None:
        self.root = root

    async def create_attempt_directory(self, claim: TaskClaim) -> Path:
        directory = self.root / claim.attempt_id
        await asyncio.to_thread(directory.mkdir, parents=True, exist_ok=True)
        return directory

    async def persist_attempt(
        self,
        claim: TaskClaim,
        directory: Path,
        snapshot_id: str,
        warc_files: tuple[Path, ...],
    ) -> tuple[ArtifactReference, ...]:
        del claim, snapshot_id
        return await asyncio.to_thread(references, directory, warc_files)

    async def discard_attempt(self, claim: TaskClaim, directory: Path) -> None:
        del claim
        await asyncio.to_thread(shutil.rmtree, directory, True)

    async def commit_attempt(self, claim: TaskClaim, directory: Path) -> None:
        del claim, directory
