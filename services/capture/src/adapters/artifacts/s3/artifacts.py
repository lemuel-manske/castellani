import asyncio
import hashlib
import shutil
from pathlib import Path
from typing import Any
from urllib.parse import quote

from domain.capture import (
    ArtifactReference,
    TaskClaim,
    WACZObject,
    WACZRangeNotSatisfiable,
    manifest_key,
)
from ports.artifacts import DecisionArtifacts, ManifestArtifacts, PackageArtifacts, WACZArtifacts
from ports.worker import ArtifactStore
from topology.buckets import ARCHIVE_ARTIFACTS_BUCKET, ARCHIVE_MANIFESTS_BUCKET
from utils.http import http_last_modified, normalize_etag, parse_range
from utils.io import stream_body

from .keys import archive_prefixes, package_key, staging_artifact_key

DEFAULT_STAGING_ROOT = Path("/tmp/castellani/capture")

DELETE_BATCH_SIZE = 1000


def file_digest(path: Path) -> str:
    digest = hashlib.sha256()

    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)

    return digest.hexdigest()


def delete_objects_by_prefix(client: Any, prefixes: tuple[str, ...]) -> int:
    deleted = 0
    paginator = client.get_paginator("list_objects_v2")

    for prefix in prefixes:
        objects: list[dict[str, str]] = []

        for page in paginator.paginate(Bucket=ARCHIVE_ARTIFACTS_BUCKET, Prefix=prefix):
            objects.extend(
                {"Key": item["Key"]}
                for item in page.get("Contents", ())
                if item.get("Key") is not None
            )

        for offset in range(0, len(objects), DELETE_BATCH_SIZE):
            batch = objects[offset : offset + DELETE_BATCH_SIZE]

            client.delete_objects(
                Bucket=ARCHIVE_ARTIFACTS_BUCKET,
                Delete={"Objects": batch, "Quiet": True},
            )

            deleted += len(batch)

    return deleted


class S3ArtifactStore(
    ArtifactStore,
    DecisionArtifacts,
    ManifestArtifacts,
    PackageArtifacts,
    WACZArtifacts,
):
    """Uploads attempt-scoped WARC artifacts to private, immutable S3 keys."""

    def __init__(
        self,
        client: Any,
        staging_root: Path = DEFAULT_STAGING_ROOT,
    ) -> None:
        self.client = client

        self.staging_root = staging_root

    async def persist_manifest(self, archive_id: str, body: bytes) -> ArtifactReference:
        def persist() -> ArtifactReference:
            digest = hashlib.sha256(body).hexdigest()
            key = manifest_key(archive_id, digest)

            self.client.put_object(
                Bucket=ARCHIVE_MANIFESTS_BUCKET,
                Key=key,
                Body=body,
                ContentType="application/json",
            )

            return ArtifactReference(
                bucket=ARCHIVE_MANIFESTS_BUCKET,
                key=key,
                sha256=digest,
                size_bytes=len(body),
            )

        return await asyncio.to_thread(persist)

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

                key = staging_artifact_key(claim, snapshot_id, relative)

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

    async def read_wacz(
        self,
        reference: ArtifactReference,
        range_header: str | None,
        if_range: str | None,
        metadata_only: bool = False,
    ) -> WACZObject:
        def read() -> WACZObject:
            request: dict[str, Any] = {
                "Bucket": reference.bucket,
                "Key": reference.key,
            }

            head = self.client.head_object(**request)

            etag = str(head["ETag"])
            content_length = int(head["ContentLength"])
            last_modified = head.get("LastModified")
            if_range_matches = if_range is None or normalize_etag(if_range) == normalize_etag(etag)
            requested = (
                parse_range(range_header, content_length)
                if range_header and if_range_matches
                else None
            )

            if requested is None:
                body = None if metadata_only else self.client.get_object(**request)["Body"]

                return WACZObject(
                    body=None if body is None else stream_body(body),
                    content_length=content_length,
                    etag=etag,
                    last_modified=http_last_modified(last_modified),
                    content_range=None,
                    partial=False,
                )

            start, end = requested

            if start >= content_length or start < 0:
                raise WACZRangeNotSatisfiable(content_length)

            end = min(end, content_length - 1) if end is not None else content_length - 1
            body = None

            if not metadata_only:
                body = self.client.get_object(
                    **request,
                    Range=f"bytes={start}-{end}",
                )["Body"]

            return WACZObject(
                body=None if body is None else stream_body(body),
                content_length=end - start + 1,
                etag=etag,
                last_modified=http_last_modified(last_modified),
                content_range=f"bytes {start}-{end}/{content_length}",
                partial=True,
            )

        return await asyncio.to_thread(read)

    async def read_object(
        self,
        bucket: str,
        key: str,
    ) -> tuple[bytes, ArtifactReference]:
        def read() -> tuple[bytes, ArtifactReference]:
            body = self.read_object_sync(bucket, key)

            return body, ArtifactReference(
                bucket=bucket,
                key=key,
                sha256=hashlib.sha256(body).hexdigest(),
                size_bytes=len(body),
            )

        return await asyncio.to_thread(read)

    async def download_artifact(self, reference: ArtifactReference, destination: Path) -> Path:
        def download() -> Path:
            body = self.read_object_sync(
                reference.bucket,
                reference.key,
            )

            sha256 = hashlib.sha256(body).hexdigest()

            if sha256 != reference.sha256:
                raise RuntimeError(f"artifact checksum mismatch for {reference.key}")

            if len(body) != reference.size_bytes:
                raise RuntimeError(f"artifact size mismatch for {reference.key}")

            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(body)

            return destination

        return await asyncio.to_thread(download)

    def read_object_sync(
        self,
        bucket: str,
        key: str,
    ) -> bytes:
        request: dict[str, Any] = {
            "Bucket": bucket,
            "Key": key,
        }

        body = self.client.get_object(**request)["Body"]

        try:
            return body.read()
        finally:
            body.close()

    async def persist_package(
        self,
        path: Path,
        archive_id: str,
        manifest_digest: str,
    ) -> ArtifactReference:
        def upload() -> ArtifactReference:
            digest = file_digest(path)

            key = package_key(archive_id, manifest_digest, digest)

            self.client.upload_file(
                str(path),
                ARCHIVE_ARTIFACTS_BUCKET,
                key,
                ExtraArgs={
                    "Metadata": {
                        "sha256": digest,
                        "manifestDigest": manifest_digest,
                    }
                },
            )

            metadata = self.client.head_object(Bucket=ARCHIVE_ARTIFACTS_BUCKET, Key=key)

            if metadata.get("Metadata", {}).get("sha256") != digest:
                raise RuntimeError(f"S3 package checksum metadata mismatch for {key}")

            size_bytes = path.stat().st_size

            if metadata.get("ContentLength") != size_bytes:
                raise RuntimeError(f"S3 package size mismatch for {key}")

            return ArtifactReference(
                bucket=ARCHIVE_ARTIFACTS_BUCKET,
                key=key,
                sha256=digest,
                size_bytes=size_bytes,
            )

        return await asyncio.to_thread(upload)

    async def delete_archive_objects(self, archive_id: str) -> int:
        def delete() -> int:
            return delete_objects_by_prefix(
                self.client,
                archive_prefixes(archive_id),
            )

        return await asyncio.to_thread(delete)
