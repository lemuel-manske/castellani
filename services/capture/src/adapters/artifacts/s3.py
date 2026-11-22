import asyncio
import hashlib
import shutil
from pathlib import Path
from typing import Any
from urllib.parse import quote

from domain import ArtifactReference, TaskClaim
from worker import ArtifactStore


class S3ArtifactStore(ArtifactStore):
    """Uploads attempt-scoped WARC artifacts to private, immutable S3 keys."""

    def __init__(self, client: Any, bucket: str, staging_root: Path) -> None:
        if not bucket:
            raise ValueError("artifact bucket must not be empty")

        self.client = client
        self.bucket = bucket
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
        return await asyncio.to_thread(
            self._persist_attempt,
            claim,
            directory,
            snapshot_id,
            warc_files,
        )

    def _persist_attempt(
        self,
        claim: TaskClaim,
        directory: Path,
        snapshot_id: str,
        warc_files: tuple[Path, ...],
    ) -> tuple[ArtifactReference, ...]:
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
                self.bucket,
                key,
                ExtraArgs={"Metadata": {"sha256": sha256}},
            )

            metadata = self.client.head_object(Bucket=self.bucket, Key=key)

            if metadata.get("Metadata", {}).get("sha256") != sha256:
                raise RuntimeError(f"S3 artifact checksum metadata mismatch for {key}")

            if metadata.get("ContentLength") != size_bytes:
                raise RuntimeError(f"S3 artifact size mismatch for {key}")

            references.append(
                ArtifactReference(
                    bucket=self.bucket,
                    key=key,
                    sha256=sha256,
                    size_bytes=size_bytes,
                    version_id=metadata.get("VersionId"),
                )
            )

        return tuple(references)

    async def discard_attempt(self, claim: TaskClaim, directory: Path) -> None:
        prefix = "/".join(
            (
                "capture-staging",
                quote(claim.task.archive_id, safe=""),
                quote(claim.task.url_key, safe=""),
                quote(claim.attempt_id, safe=""),
            )
        ) + "/"

        await asyncio.to_thread(self._discard_attempt_objects, prefix)
        await asyncio.to_thread(shutil.rmtree, directory, True)

    def _discard_attempt_objects(self, prefix: str) -> None:
        key_marker: str | None = None
        version_marker: str | None = None

        while True:
            request: dict[str, Any] = {
                "Bucket": self.bucket,
                "Prefix": prefix,
            }

            if key_marker is not None:
                request["KeyMarker"] = key_marker

            if version_marker is not None:
                request["VersionIdMarker"] = version_marker

            page = self.client.list_object_versions(**request)
            versions = page.get("Versions", [])
            delete_markers = page.get("DeleteMarkers", [])
            objects = [
                {"Key": item["Key"], "VersionId": item["VersionId"]}
                for item in (*versions, *delete_markers)
            ]

            for offset in range(0, len(objects), 1000):
                response = self.client.delete_objects(
                    Bucket=self.bucket,
                    Delete={"Objects": objects[offset : offset + 1000], "Quiet": True},
                )

                if response.get("Errors"):
                    raise RuntimeError(
                        f"failed to delete staged S3 artifacts under {prefix}"
                    )

            if not page.get("IsTruncated"):
                return

            key_marker = page.get("NextKeyMarker")
            version_marker = page.get("NextVersionIdMarker")

            if key_marker is None:
                raise RuntimeError("S3 returned a truncated version listing without a key marker")

    async def commit_attempt(self, claim: TaskClaim, directory: Path) -> None:
        del claim

        await asyncio.to_thread(shutil.rmtree, directory, True)
