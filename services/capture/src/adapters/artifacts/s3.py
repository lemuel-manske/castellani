import asyncio
import hashlib
import shutil
from pathlib import Path
from typing import Any
from urllib.parse import quote

from buckets import ARCHIVE_ARTIFACTS_BUCKET
from domain import ArtifactReference, TaskClaim
from worker import ArtifactStore

DEFAULT_STAGING_ROOT = Path("/tmp/castellani/capture")


class S3ArtifactStore(ArtifactStore):
    """Uploads attempt-scoped WARC artifacts to private, immutable S3 keys."""

    def __init__(
        self,
        client: Any,
        staging_root: Path = DEFAULT_STAGING_ROOT,
    ) -> None:
        self.client = client

        self.staging_root = staging_root

    async def create_attempt_directory(self, claim: TaskClaim) -> Path:
        directory = self.staging_root / quote(claim.attempt_id, safe="")

        await asyncio.to_thread(directory.mkdir, parents=True, exist_ok=True)

        return directory

    async def persist_attempt(
        self,
        claim: TaskClaim,
        directory: Path,
        snapshot_id: str,
        warc_files: tuple[Path, ...],
    ) -> tuple[ArtifactReference, ...]:
        def upload_artifacts() -> tuple[ArtifactReference, ...]:
            if not warc_files:
                raise ValueError("a capture must produce at least one WARC file")

            root = directory.resolve(strict=True)

            references: list[ArtifactReference] = []
            seen_keys: set[str] = set()

            for path in warc_files:
                resolved = path.resolve(strict=True)

                if not resolved.is_file():
                    raise ValueError(f"capture artifact is not a regular file: {path}")

                relative = resolved.relative_to(root)

                if relative in (Path("."), Path("")):
                    raise ValueError("capture artifact must have a relative file name")

                key = "/".join(
                    (
                        "capture-staging",
                        quote(claim.task.archive_id, safe=""),
                        quote(claim.task.url_key, safe=""),
                        quote(claim.attempt_id, safe=""),
                        quote(snapshot_id, safe=""),
                        *(quote(part, safe="") for part in relative.parts),
                    )
                )

                if key in seen_keys:
                    raise ValueError(f"duplicate artifact key: {key}")

                seen_keys.add(key)

                digest = hashlib.sha256()

                with resolved.open("rb") as stream:
                    for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                        digest.update(chunk)

                sha256 = digest.hexdigest()

                size_bytes = resolved.stat().st_size

                self.client.upload_file(
                    str(resolved),
                    ARCHIVE_ARTIFACTS_BUCKET,
                    key,
                    ExtraArgs={"Metadata": {"sha256": sha256}},
                )

                metadata = self.client.head_object(Bucket=ARCHIVE_ARTIFACTS_BUCKET, Key=key)

                if metadata.get("Metadata", {}).get("sha256") != sha256:
                    raise RuntimeError(f"S3 artifact checksum metadata mismatch for {key}")

                if metadata.get("ContentLength") != size_bytes:
                    raise RuntimeError(f"S3 artifact size mismatch for {key}")

                references.append(
                    ArtifactReference(
                        bucket=ARCHIVE_ARTIFACTS_BUCKET,
                        key=key,
                        sha256=sha256,
                        size_bytes=size_bytes,
                        version_id=metadata.get("VersionId"),
                    )
                )

            return tuple(references)

        return await asyncio.to_thread(upload_artifacts)

    async def discard_attempt(self, claim: TaskClaim, directory: Path) -> None:
        del claim

        await asyncio.to_thread(shutil.rmtree, directory, True)

    async def commit_attempt(self, claim: TaskClaim, directory: Path) -> None:
        del claim

        await asyncio.to_thread(shutil.rmtree, directory, True)
