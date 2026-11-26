import hashlib
from pathlib import Path

import pytest
from mypy_boto3_s3.client import S3Client
from support.domain import make_claim
from support.s3 import object_keys, put_object, read_object

from adapters.artifacts.s3 import S3ArtifactStore
from domain.capture import ArtifactReference
from topology.buckets import ARCHIVE_ARTIFACTS_BUCKET


@pytest.mark.integration
@pytest.mark.asyncio
async def test_s3_artifact_store_uploads_immutable_attempt_scoped_objects(
    tmp_path: Path,
    s3: S3Client,
) -> None:
    store = S3ArtifactStore(s3, tmp_path)

    claim = make_claim()

    directory = await store.create_attempt_directory(claim)

    warc = directory / "records" / "capture.warc.gz"
    warc.parent.mkdir()
    warc.write_bytes(b"warc-content")

    references = await store.persist_attempt(
        claim,
        directory,
        "snapshot-1",
        (warc,),
    )

    assert len(references) == 1

    reference = references[0]

    assert reference.bucket == ARCHIVE_ARTIFACTS_BUCKET

    assert reference.key.startswith("capture-staging/archive%2Fone/url-key/attempt-1/")
    assert reference.key.endswith("records/capture.warc.gz")

    assert reference.sha256
    assert reference.size_bytes == len(b"warc-content")

    assert read_object(s3, ARCHIVE_ARTIFACTS_BUCKET, reference.key) == b"warc-content"
    assert reference.key in object_keys(s3, ARCHIVE_ARTIFACTS_BUCKET)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_s3_artifact_store_reads_object_with_reference(s3: S3Client) -> None:
    put_object(s3, ARCHIVE_ARTIFACTS_BUCKET, "read-object-key", b"manifest")

    body, reference = await S3ArtifactStore(s3).read_object(
        ARCHIVE_ARTIFACTS_BUCKET,
        "read-object-key",
    )

    assert (body, reference) == (
        b"manifest",
        ArtifactReference(
            bucket=ARCHIVE_ARTIFACTS_BUCKET,
            key="read-object-key",
            sha256=hashlib.sha256(b"manifest").hexdigest(),
            size_bytes=len(b"manifest"),
        ),
    )


@pytest.mark.integration
@pytest.mark.asyncio
async def test_s3_artifact_store_rejects_files_outside_attempt_directory(
    tmp_path: Path,
    s3: S3Client,
) -> None:
    store = S3ArtifactStore(s3, tmp_path)

    claim = make_claim()

    directory = await store.create_attempt_directory(claim)

    outside = tmp_path / "outside.warc.gz"
    outside.write_bytes(b"not attempt-owned")

    with pytest.raises(ValueError):
        await store.persist_attempt(claim, directory, "snapshot-1", (outside,))


@pytest.mark.integration
@pytest.mark.asyncio
async def test_s3_artifact_store_addresses_packages_by_content_digest(
    tmp_path: Path,
    s3: S3Client,
) -> None:
    store = S3ArtifactStore(s3)

    first = tmp_path / "first.wacz"
    first.write_bytes(b"first-package")
    second = tmp_path / "second.wacz"
    second.write_bytes(b"second-package")
    duplicate = tmp_path / "duplicate.wacz"
    duplicate.write_bytes(b"first-package")

    first_reference = await store.persist_package(first, "archive-1", "a" * 64)
    second_reference = await store.persist_package(second, "archive-1", "a" * 64)
    duplicate_reference = await store.persist_package(duplicate, "archive-1", "a" * 64)

    assert first_reference.key != second_reference.key
    assert first_reference.key == duplicate_reference.key
    assert first_reference.sha256 in first_reference.key
    assert second_reference.sha256 in second_reference.key

    assert read_object(s3, first_reference.bucket, first_reference.key) == b"first-package"
    assert read_object(s3, second_reference.bucket, second_reference.key) == b"second-package"
